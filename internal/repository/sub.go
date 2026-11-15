package repository

import (
	"context"
	"errors"

	"gorm.io/gorm"
)

type Sub struct {
	ID        string    `gorm:"type:varchar(32);primaryKey"`
	Name      string    `gorm:"size:255;not null"`
	BaseURL   string    `gorm:"type:text;not null"`
	Email     string    `gorm:"size:255;not null"`
	Password  string    `gorm:"type:text;not null"`
	APIKey    string    `gorm:"type:text;not null"`
	GroupID   string    `gorm:"size:255;not null"`
	ImportJob ImportJob `gorm:"embedded"`
}

func (Sub) TableName() string { return "subs" }

func (r *Repository) Subs(ctx context.Context) ([]Sub, error) {
	var items []Sub
	err := r.db.WithContext(ctx).Order("name").Find(&items).Error
	for index := range items {
		items[index].ImportJob.normalize()
	}
	return items, err
}

func (r *Repository) Sub(ctx context.Context, id string) (Sub, error) {
	var item Sub
	if err := r.db.WithContext(ctx).First(&item, "id = ?", id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return Sub{}, ErrNotFound
		}
		return Sub{}, err
	}
	item.ImportJob.normalize()
	return item, nil
}

func (r *Repository) SaveSub(ctx context.Context, item Sub) error {
	item.ImportJob.normalize()
	return r.db.WithContext(ctx).Save(&item).Error
}

func (r *Repository) DeleteSub(ctx context.Context, id string) error {
	return r.db.WithContext(ctx).Delete(&Sub{}, "id = ?", id).Error
}

func (r *Repository) FailSubImports(ctx context.Context, updatedAt string) error {
	return r.db.WithContext(ctx).Model(&Sub{}).Where("import_status IN ?", []string{"pending", "running"}).Updates(map[string]any{"import_status": "failed", "import_updated_at": updatedAt}).Error
}
