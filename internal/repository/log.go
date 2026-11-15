package repository

import (
	"context"
	"time"
)

type Log struct {
	ID         string         `gorm:"type:varchar(32);primaryKey"`
	Time       time.Time      `gorm:"not null;index:idx_logs_time_status,priority:1"`
	Status     string         `gorm:"size:16;not null;default:'';index:idx_logs_time_status,priority:2"`
	Model      string         `gorm:"size:255;not null;default:''"`
	DurationMS float64        `gorm:"not null;default:0"`
	Summary    string         `gorm:"type:text;not null"`
	Detail     map[string]any `gorm:"not null;serializer:json"`
}

func (Log) TableName() string { return "logs" }

func (r *Repository) Logs(ctx context.Context, startDate string, endDate string, page int, pageSize int) ([]Log, int64, error) {
	db := r.db.WithContext(ctx).Model(&Log{})
	if startDate != "" {
		db = db.Where("time >= ?", startDate)
	}
	if endDate != "" {
		end, err := time.Parse("2006-01-02", endDate)
		if err != nil {
			return nil, 0, err
		}
		db = db.Where("time < ?", end.AddDate(0, 0, 1).Format("2006-01-02"))
	}
	var total int64
	if err := db.Count(&total).Error; err != nil {
		return nil, 0, err
	}
	var items []Log
	if err := db.Order("time DESC").Offset((page - 1) * pageSize).Limit(pageSize).Find(&items).Error; err != nil {
		return nil, 0, err
	}
	return items, total, nil
}

func (r *Repository) SaveLog(ctx context.Context, item Log) error {
	item.Status, item.Model, item.DurationMS = logColumns(item.Detail)
	return r.db.WithContext(ctx).Save(&item).Error
}

func (r *Repository) UpdateLog(ctx context.Context, id string, summary string, detail map[string]any) error {
	status, model, duration := logColumns(detail)
	// Update through the model so Gorm applies Detail's JSON serializer.
	result := r.db.WithContext(ctx).Model(&Log{}).Where("id = ?", id).Updates(Log{Summary: summary, Detail: detail, Status: status, Model: model, DurationMS: duration})
	if result.Error != nil {
		return result.Error
	}
	if result.RowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}

// logColumns 把概览统计用的状态、模型、耗时从详情里取出来单独存列
func logColumns(detail map[string]any) (string, string, float64) {
	status, _ := detail["status"].(string)
	model, _ := detail["model"].(string)
	duration := 0.0
	switch value := detail["duration_ms"].(type) {
	case int64:
		duration = float64(value)
	case float64:
		duration = value
	}
	return status, model, duration
}

func (r *Repository) DeleteLogsBefore(ctx context.Context, cutoff time.Time) error {
	return r.db.WithContext(ctx).Where("time < ?", cutoff).Delete(&Log{}).Error
}

func (r *Repository) DeleteLogs(ctx context.Context, ids []string) (int64, error) {
	result := r.db.WithContext(ctx).Where("id IN ?", ids).Delete(&Log{})
	return result.RowsAffected, result.Error
}
