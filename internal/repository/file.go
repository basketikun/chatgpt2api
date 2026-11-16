package repository

import (
	"context"
	"errors"

	"gorm.io/gorm"
)

type File struct {
	ID          int64  `gorm:"primaryKey"`
	Path        string `gorm:"type:text;not null;uniqueIndex"`
	Kind        string `gorm:"size:32;not null;index"`
	Name        string `gorm:"size:255;not null"`
	Date        string `gorm:"size:10;not null;index"`
	Size        int64  `gorm:"not null"`
	ContentType string `gorm:"size:128;not null"`
	Storage     string `gorm:"size:16;not null"`
	Local       bool   `gorm:"not null"`
	WebDAV      bool   `gorm:"not null"`
	RemoteURL   string `gorm:"type:text;not null"`
	Width       *int
	Height      *int
	CreatedAt   string `gorm:"size:32;not null;index"`
}

func (File) TableName() string { return "files" }

func (r *Repository) Files(ctx context.Context, kind string) ([]File, error) {
	db := r.db.WithContext(ctx).Order("created_at DESC")
	if kind != "" {
		db = db.Where("kind = ?", kind)
	}
	var items []File
	err := db.Find(&items).Error
	return items, err
}

func (r *Repository) File(ctx context.Context, path string) (File, error) {
	var item File
	if err := r.db.WithContext(ctx).Where("path = ?", path).First(&item).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return File{}, ErrNotFound
		}
		return File{}, err
	}
	return item, nil
}

func (r *Repository) SaveFile(ctx context.Context, item File) error {
	return r.db.WithContext(ctx).Where("path = ?", item.Path).Assign(item).FirstOrCreate(&item).Error
}

func (r *Repository) DeleteFile(ctx context.Context, path string) error {
	return r.db.WithContext(ctx).Where("path = ?", path).Delete(&File{}).Error
}
