package repository

import (
	"context"
	"errors"

	"gorm.io/gorm"
)

type CPA struct {
	ID        string    `gorm:"type:varchar(32);primaryKey"`
	Name      string    `gorm:"size:255;not null"`
	BaseURL   string    `gorm:"type:text;not null"`
	SecretKey string    `gorm:"type:text;not null"`
	ImportJob ImportJob `gorm:"embedded"`
}

func (CPA) TableName() string { return "cpas" }

func (r *Repository) CPAs(ctx context.Context) ([]CPA, error) {
	var items []CPA
	err := r.db.WithContext(ctx).Order("name").Find(&items).Error
	for index := range items {
		items[index].ImportJob.normalize()
	}
	return items, err
}

func (r *Repository) CPA(ctx context.Context, id string) (CPA, error) {
	var item CPA
	if err := r.db.WithContext(ctx).First(&item, "id = ?", id).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return CPA{}, ErrNotFound
		}
		return CPA{}, err
	}
	item.ImportJob.normalize()
	return item, nil
}

func (r *Repository) SaveCPA(ctx context.Context, item CPA) error {
	item.ImportJob.normalize()
	return r.db.WithContext(ctx).Save(&item).Error
}

func (r *Repository) DeleteCPA(ctx context.Context, id string) error {
	return r.db.WithContext(ctx).Delete(&CPA{}, "id = ?", id).Error
}

func (r *Repository) FailCPAImports(ctx context.Context, updatedAt string) error {
	return r.db.WithContext(ctx).Model(&CPA{}).Where("import_status IN ?", []string{"pending", "running"}).Updates(map[string]any{"import_status": "failed", "import_updated_at": updatedAt}).Error
}

type ImportJob struct {
	ID        string           `json:"job_id" gorm:"column:import_job_id;size:32;not null"`
	Status    string           `json:"status" gorm:"column:import_status;size:16;not null"`
	CreatedAt string           `json:"created_at" gorm:"column:import_created_at;size:40;not null"`
	UpdatedAt string           `json:"updated_at" gorm:"column:import_updated_at;size:40;not null"`
	Total     int              `json:"total" gorm:"column:import_total;not null;default:0"`
	Completed int              `json:"completed" gorm:"column:import_completed;not null;default:0"`
	Added     int              `json:"added" gorm:"column:import_added;not null;default:0"`
	Skipped   int              `json:"skipped" gorm:"column:import_skipped;not null;default:0"`
	Refreshed int              `json:"refreshed" gorm:"column:import_refreshed;not null;default:0"`
	Failed    int              `json:"failed" gorm:"column:import_failed;not null;default:0"`
	Errors    []map[string]any `json:"errors" gorm:"column:import_errors;not null;serializer:json"`
}

func (job *ImportJob) normalize() {
	if job.Errors == nil {
		job.Errors = []map[string]any{}
	}
}
