package repository

import (
	"context"
	"errors"
	"slices"
	"time"

	"gorm.io/gorm"
)

type Account struct {
	ID            int64   `gorm:"primaryKey"`
	AccessToken   string  `gorm:"type:text;not null"`
	RefreshToken  string  `gorm:"type:text;not null"`
	IDToken       string  `gorm:"type:text;not null"`
	Email         *string `gorm:"size:255;uniqueIndex"`
	UserID        *string `gorm:"size:255"`
	AccountID     string  `gorm:"size:255;not null"`
	Type          string  `gorm:"size:32;not null;default:free"`
	IsCodex       bool    `gorm:"not null;default:false"`
	Status        string  `gorm:"size:32;not null;default:正常"`
	Quota         int     `gorm:"not null;default:0"`
	Proxy         string  `gorm:"type:text;not null"`
	Remaining     int     `gorm:"not null;default:0"`
	ResetAfter    *string `gorm:"size:64"`
	Success       int     `gorm:"not null;default:0"`
	Fail          int     `gorm:"not null;default:0"`
	LastUsedAt    *string `gorm:"size:32"`
	LastRefreshAt *string `gorm:"size:32"`
	LastError     *string `gorm:"type:text"`
	CreatedAt     string  `gorm:"size:32;not null"`
	ImageInflight int     `gorm:"not null;default:0"`
}

func (Account) TableName() string { return "accounts" }

func (r *Repository) AccountPage(ctx context.Context, page int, pageSize int, query string, accountType string, status string) ([]Account, int64, []string, error) {
	db := r.db.WithContext(ctx).Model(&Account{})
	if query != "" {
		operator := "LIKE"
		if r.db.Dialector.Name() == "postgres" {
			operator = "ILIKE"
		}
		db = db.Where("email "+operator+" ?", "%"+query+"%")
	}
	if accountType != "" {
		db = db.Where("type = ?", accountType)
	}
	if status != "" {
		db = db.Where("status = ?", status)
	}
	var total int64
	if err := db.Count(&total).Error; err != nil {
		return nil, 0, nil, err
	}
	var items []Account
	if err := db.Order("id").Offset((page - 1) * pageSize).Limit(pageSize).Find(&items).Error; err != nil {
		return nil, 0, nil, err
	}
	var types []string
	if err := r.db.WithContext(ctx).Model(&Account{}).Distinct().Order("type").Pluck("type", &types).Error; err != nil {
		return nil, 0, nil, err
	}
	return items, total, types, nil
}

func (r *Repository) Accounts(ctx context.Context) ([]Account, error) {
	var items []Account
	err := r.db.WithContext(ctx).Order("id").Find(&items).Error
	return items, err
}

func (r *Repository) AccountTypeCounts(ctx context.Context) (map[string]int64, error) {
	var rows []struct {
		Type  string
		Count int64
	}
	if err := r.db.WithContext(ctx).Model(&Account{}).Select("type, count(*) AS count").Where("status NOT IN ?", []string{"禁用", "异常"}).Group("type").Scan(&rows).Error; err != nil {
		return nil, err
	}
	result := make(map[string]int64, len(rows))
	for _, row := range rows {
		result[row.Type] = row.Count
	}
	return result, nil
}

func (r *Repository) ActiveAccounts(ctx context.Context) ([]Account, error) {
	var items []Account
	err := r.db.WithContext(ctx).Where("status NOT IN ?", []string{"禁用", "异常"}).Order("id").Find(&items).Error
	return items, err
}

// NextTextAccount 取最久未使用的可用账号；types 为 nil 表示不限套餐
func (r *Repository) NextTextAccount(ctx context.Context, types []string, excludedEmails []string) (Account, error) {
	db := r.db.WithContext(ctx).Where("access_token <> '' AND status NOT IN ?", []string{"禁用", "异常"})
	if types != nil {
		db = db.Where("type IN ?", types)
	}
	if len(excludedEmails) > 0 {
		db = db.Where("email NOT IN ?", excludedEmails)
	}
	var item Account
	if err := db.Order("COALESCE(last_used_at, '') ASC, id ASC").First(&item).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return Account{}, ErrNotFound
		}
		return Account{}, err
	}
	return item, nil
}

func (r *Repository) AccountByEmail(ctx context.Context, email string) (Account, error) {
	var item Account
	if err := r.db.WithContext(ctx).Where("email = ?", email).First(&item).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return Account{}, ErrNotFound
		}
		return Account{}, err
	}
	return item, nil
}

func (r *Repository) AccountByID(ctx context.Context, id int64) (Account, error) {
	var item Account
	if err := r.db.WithContext(ctx).First(&item, id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return Account{}, ErrNotFound
		}
		return Account{}, err
	}
	return item, nil
}

func (r *Repository) SaveAccounts(ctx context.Context, items []Account) (int, int, error) {
	added, updated := 0, 0
	err := r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		for _, item := range items {
			var current Account
			err := tx.Where("email = ?", item.Email).First(&current).Error
			if err == nil {
				item.ID = current.ID
				updated++
			} else if errors.Is(err, gorm.ErrRecordNotFound) {
				added++
			} else {
				return err
			}
			if err := tx.Save(&item).Error; err != nil {
				return err
			}
		}
		return nil
	})
	return added, updated, err
}

func (r *Repository) DeleteAccounts(ctx context.Context, emails []string) (int64, error) {
	result := r.db.WithContext(ctx).Where("email IN ?", emails).Delete(&Account{})
	return result.RowsAffected, result.Error
}

func (r *Repository) UpdateAccount(ctx context.Context, email string, values map[string]any) (Account, error) {
	result := r.db.WithContext(ctx).Model(&Account{}).Where("email = ?", email).Updates(values)
	if result.Error != nil {
		return Account{}, result.Error
	}
	if result.RowsAffected == 0 {
		return Account{}, ErrNotFound
	}
	return r.AccountByEmail(ctx, email)
}

func (r *Repository) ReplaceAccountToken(ctx context.Context, email string, item Account) (Account, error) {
	values := map[string]any{
		"access_token":    item.AccessToken,
		"refresh_token":   item.RefreshToken,
		"id_token":        item.IDToken,
		"email":           item.Email,
		"user_id":         item.UserID,
		"account_id":      item.AccountID,
		"type":            item.Type,
		"is_codex":        item.IsCodex,
		"proxy":           item.Proxy,
		"last_refresh_at": item.LastRefreshAt,
		"last_error":      item.LastError,
	}
	result := r.db.WithContext(ctx).Model(&Account{}).Where("email = ?", email).Updates(values)
	if result.Error != nil {
		return Account{}, result.Error
	}
	if result.RowsAffected == 0 {
		return Account{}, ErrNotFound
	}
	return r.AccountByEmail(ctx, email)
}

func (r *Repository) TouchAccount(ctx context.Context, email string, now string) error {
	result := r.db.WithContext(ctx).Model(&Account{}).Where("email = ?", email).Update("last_used_at", now)
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}

func (r *Repository) AcquireImageAccount(ctx context.Context, routes []string, plans []string, concurrency int, attempted map[string]bool) (Account, bool, error) {
	var candidates []Account
	db := r.db.WithContext(ctx).Where("status = ? AND quota > 0", "正常")
	webRoute := slices.Contains(routes, "web")
	if !webRoute {
		db = db.Where("is_codex = ?", true)
	}
	if len(plans) > 0 {
		db = db.Where("type IN ?", plans)
	}
	if err := db.Select("id", "email").Order("last_used_at ASC, id ASC").Limit(100).Find(&candidates).Error; err != nil {
		return Account{}, false, err
	}
	now := time.Now().UTC().Format(time.RFC3339)
	for _, candidate := range candidates {
		if attempted[*candidate.Email] {
			continue
		}
		claim := r.db.WithContext(ctx).Model(&Account{}).Where(
			"id = ? AND status = ? AND quota > 0 AND image_inflight < ?",
			candidate.ID, "正常", concurrency,
		)
		if !webRoute {
			claim = claim.Where("is_codex = ?", true)
		}
		if len(plans) > 0 {
			claim = claim.Where("type IN ?", plans)
		}
		result := claim.Updates(map[string]any{"image_inflight": gorm.Expr("image_inflight + ?", 1), "last_used_at": now})
		if result.Error != nil {
			return Account{}, false, result.Error
		}
		if result.RowsAffected == 0 {
			continue
		}
		item, err := r.AccountByID(ctx, candidate.ID)
		if err != nil {
			return Account{}, false, err
		}
		return item, true, nil
	}
	return Account{}, false, nil
}

// ImageAccountAvailable 判断是否还有本次请求未尝试过、当前可用的图片账号。
// 被并发占满但仍能轮到的账号算可用（调用方应继续等待）；已尝试过的账号不算，
// 避免账号都试过一遍后还在空转。
func (r *Repository) ImageAccountAvailable(ctx context.Context, routes []string, plans []string, attempted map[string]bool) (bool, error) {
	db := r.db.WithContext(ctx).Model(&Account{}).Where("status = ? AND quota > 0", "正常")
	if !slices.Contains(routes, "web") {
		db = db.Where("is_codex = ?", true)
	}
	if len(plans) > 0 {
		db = db.Where("type IN ?", plans)
	}
	if len(attempted) > 0 {
		emails := make([]string, 0, len(attempted))
		for email := range attempted {
			emails = append(emails, email)
		}
		db = db.Where("email NOT IN ?", emails)
	}
	var count int64
	if err := db.Count(&count).Error; err != nil {
		return false, err
	}
	return count > 0, nil
}

func (r *Repository) ReleaseImageAccount(ctx context.Context, email string, success bool, now string) (Account, error) {
	values := map[string]any{
		"image_inflight": gorm.Expr("CASE WHEN image_inflight > 0 THEN image_inflight - 1 ELSE 0 END"),
		"last_used_at":   now,
	}
	if success {
		values["success"] = gorm.Expr("success + 1")
		values["quota"] = gorm.Expr("CASE WHEN quota > 0 THEN quota - 1 ELSE 0 END")
		values["remaining"] = gorm.Expr("CASE WHEN remaining > 0 THEN remaining - 1 ELSE 0 END")
		values["status"] = gorm.Expr("CASE WHEN quota <= 1 THEN ? WHEN status = ? THEN ? ELSE status END", "限流", "限流", "正常")
	} else {
		values["fail"] = gorm.Expr("fail + 1")
	}
	result := r.db.WithContext(ctx).Model(&Account{}).Where("email = ?", email).Updates(values)
	if result.Error != nil {
		return Account{}, result.Error
	}
	if result.RowsAffected == 0 {
		return Account{}, ErrNotFound
	}
	return r.AccountByEmail(ctx, email)
}

func (r *Repository) ReleaseImageAccountByID(ctx context.Context, id int64) error {
	result := r.db.WithContext(ctx).Model(&Account{}).Where("id = ?", id).Update("image_inflight", gorm.Expr("CASE WHEN image_inflight > 0 THEN image_inflight - 1 ELSE 0 END"))
	return result.Error
}

func (r *Repository) ResetAccountImageInflight(ctx context.Context) error {
	return r.db.WithContext(ctx).Model(&Account{}).Where("image_inflight > 0").Update("image_inflight", 0).Error
}

func (r *Repository) AccountSummary(ctx context.Context) (map[string]int64, error) {
	var rows []struct {
		Status string
		Count  int64
		Quota  int64
	}
	if err := r.db.WithContext(ctx).Model(&Account{}).Select("status, count(*) AS count, coalesce(sum(remaining), 0) AS quota").Group("status").Scan(&rows).Error; err != nil {
		return nil, err
	}
	var inflight int64
	if err := r.db.WithContext(ctx).Model(&Account{}).Select("coalesce(sum(image_inflight), 0)").Scan(&inflight).Error; err != nil {
		return nil, err
	}
	result := map[string]int64{"total": 0, "active": 0, "limited": 0, "abnormal": 0, "disabled": 0, "quota": 0, "inflight": inflight}
	for _, row := range rows {
		result["total"] += row.Count
		switch row.Status {
		case "正常":
			result["active"], result["quota"] = row.Count, row.Quota
		case "限流":
			result["limited"] = row.Count
		case "异常":
			result["abnormal"] = row.Count
		case "禁用":
			result["disabled"] = row.Count
		}
	}
	return result, nil
}
