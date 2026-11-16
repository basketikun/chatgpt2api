package repository

import (
	"context"
	"errors"
	"time"

	"gorm.io/gorm"
)

type Conversation struct {
	ID        int64          `gorm:"primaryKey"`
	OwnerID   string         `gorm:"size:255;not null;index"`
	Title     string         `gorm:"size:255;not null"`
	Type      string         `gorm:"size:32;not null;index"`
	Model     string         `gorm:"size:255;not null"`
	Messages  any            `gorm:"not null;serializer:json"`
	Extra     map[string]any `gorm:"not null;serializer:json"`
	CreatedAt time.Time      `gorm:"not null;index"`
	UpdatedAt time.Time      `gorm:"not null;index"`
}

func (Conversation) TableName() string { return "conversations" }

func (r *Repository) Conversations(ctx context.Context, ownerID string, conversationType string) ([]Conversation, error) {
	db := r.db.WithContext(ctx).Select("id", "title", "type").Where("owner_id = ?", ownerID)
	if conversationType != "" {
		db = db.Where("type = ?", conversationType)
	}
	var items []Conversation
	err := db.Order("updated_at DESC").Find(&items).Error
	return items, err
}

func (r *Repository) Conversation(ctx context.Context, ownerID string, id int64) (Conversation, error) {
	var item Conversation
	if err := r.db.WithContext(ctx).Where("owner_id = ? AND id = ?", ownerID, id).First(&item).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return Conversation{}, ErrNotFound
		}
		return Conversation{}, err
	}
	return item, nil
}

func (r *Repository) SaveConversation(ctx context.Context, item Conversation) (Conversation, error) {
	err := r.db.WithContext(ctx).Save(&item).Error
	return item, err
}

func (r *Repository) DeleteConversation(ctx context.Context, ownerID string, id int64) (bool, error) {
	result := r.db.WithContext(ctx).Where("owner_id = ? AND id = ?", ownerID, id).Delete(&Conversation{})
	return result.RowsAffected > 0, result.Error
}

func (r *Repository) DeleteConversations(ctx context.Context, ownerID string, conversationType string) (int64, error) {
	db := r.db.WithContext(ctx).Where("owner_id = ?", ownerID)
	if conversationType != "" {
		db = db.Where("type = ?", conversationType)
	}
	result := db.Delete(&Conversation{})
	return result.RowsAffected, result.Error
}
