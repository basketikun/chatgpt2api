package repository

import (
	"context"
	"errors"
	"time"

	"gorm.io/gorm"
)

type Task struct {
	ID             int64  `gorm:"primaryKey"`
	OwnerID        string `gorm:"size:255;not null;index"`
	HistoryID      *int64 `gorm:"index"`
	TurnID         *int64 `gorm:"index"`
	Title          string `gorm:"size:255;not null"`
	Type           string `gorm:"size:32;not null;index"`
	Status         string `gorm:"size:32;not null;index"`
	Prompt         string `gorm:"type:text;not null"`
	PromptDeleted  bool   `gorm:"not null;default:false"`
	ResultsDeleted bool   `gorm:"not null;default:false"`
	Model          string `gorm:"size:255;not null"`
	Size           string `gorm:"size:32;not null"`
	Quality        string `gorm:"size:32;not null"`
	OutputCount    int    `gorm:"not null;default:1"`
	ConversationID string `gorm:"type:text;not null"`
	BaseURL        string `gorm:"type:text;not null"`
	Error          string `gorm:"type:text;not null"`
	Progress       string `gorm:"size:128;not null"`
	AccountEmail   string `gorm:"size:255;not null"`
	DurationMS     *int
	InputTokens    int       `gorm:"not null;default:0"`
	OutputTokens   int       `gorm:"not null;default:0"`
	TotalTokens    int       `gorm:"not null;default:0"`
	CreatedAt      time.Time `gorm:"not null;index"`
	UpdatedAt      time.Time `gorm:"not null;index"`
	StartedAt      *time.Time
	EndedAt        *time.Time
	Results        []TaskResult `gorm:"foreignKey:TaskID;constraint:OnDelete:CASCADE"`
}

func (Task) TableName() string { return "tasks" }

func (t Task) ElapsedSeconds() float64 {
	start := t.CreatedAt
	if t.StartedAt != nil {
		start = *t.StartedAt
	}
	end := time.Now().UTC()
	if t.EndedAt != nil {
		end = *t.EndedAt
	}
	return max(0, end.Sub(start).Seconds())
}

func (r *Repository) Tasks(ctx context.Context, ownerID string, ids []int64, types []string) ([]Task, error) {
	db := r.db.WithContext(ctx).Preload("Results", func(db *gorm.DB) *gorm.DB { return db.Order("position") }).Where("owner_id = ?", ownerID)
	if len(ids) > 0 {
		db = db.Where("id IN ?", ids)
	}
	if len(types) > 0 {
		db = db.Where("type IN ?", types)
	}
	var items []Task
	if len(ids) == 0 {
		db = db.Limit(500)
	}
	err := db.Order("updated_at DESC").Find(&items).Error
	return items, err
}

func (r *Repository) CountActiveTasks(ctx context.Context, ownerID string) (int64, error) {
	var count int64
	err := r.db.WithContext(ctx).Model(&Task{}).Where("owner_id = ? AND status IN ?", ownerID, []string{"queued", "running"}).Count(&count).Error
	return count, err
}

func (r *Repository) Task(ctx context.Context, ownerID string, id int64) (Task, error) {
	var item Task
	if err := r.db.WithContext(ctx).Preload("Results", func(db *gorm.DB) *gorm.DB { return db.Order("position") }).Where("owner_id = ? AND id = ?", ownerID, id).First(&item).Error; err != nil {
		if errors.Is(err, gorm.ErrRecordNotFound) {
			return Task{}, ErrNotFound
		}
		return Task{}, err
	}
	return item, nil
}

func (r *Repository) SaveTask(ctx context.Context, item Task) (Task, error) {
	if item.ID == 0 {
		if err := r.db.WithContext(ctx).Omit("Results").Create(&item).Error; err != nil {
			return Task{}, err
		}
		return item, nil
	}
	values := map[string]any{"title": item.Title, "history_id": item.HistoryID, "turn_id": item.TurnID, "type": item.Type, "status": item.Status, "prompt": item.Prompt, "prompt_deleted": item.PromptDeleted, "results_deleted": item.ResultsDeleted, "model": item.Model, "size": item.Size, "quality": item.Quality, "output_count": item.OutputCount, "conversation_id": item.ConversationID, "base_url": item.BaseURL, "error": item.Error, "progress": item.Progress, "account_email": item.AccountEmail, "duration_ms": item.DurationMS, "input_tokens": item.InputTokens, "output_tokens": item.OutputTokens, "total_tokens": item.TotalTokens, "updated_at": item.UpdatedAt, "started_at": item.StartedAt, "ended_at": item.EndedAt}
	if err := r.db.WithContext(ctx).Model(&Task{}).Where("id = ?", item.ID).Updates(values).Error; err != nil {
		return Task{}, err
	}
	return item, nil
}

func (r *Repository) ReplaceTaskResults(ctx context.Context, taskID int64, items []TaskResult) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		if err := tx.Where("task_id = ?", taskID).Delete(&TaskResult{}).Error; err != nil {
			return err
		}
		for _, item := range items {
			item.TaskID = taskID
			if err := tx.Create(&item).Error; err != nil {
				return err
			}
		}
		return nil
	})
}

func (r *Repository) FailRunningTasks(ctx context.Context, now time.Time) error {
	return r.db.WithContext(ctx).Model(&Task{}).Where("status IN ?", []string{"queued", "running"}).Updates(map[string]any{"status": "error", "error": "服务已重启，未完成的任务已中断", "updated_at": now, "ended_at": now}).Error
}

func (r *Repository) DeleteFinishedTasksBefore(ctx context.Context, cutoff time.Time) error {
	return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
		ids := tx.Model(&Task{}).Select("id").Where("status IN ? AND updated_at < ?", []string{"success", "error"}, cutoff)
		if err := tx.Where("task_id IN (?)", ids).Delete(&TaskResult{}).Error; err != nil {
			return err
		}
		return tx.Where("status IN ? AND updated_at < ?", []string{"success", "error"}, cutoff).Delete(&Task{}).Error
	})
}

type TaskResult struct {
	ID            int64  `gorm:"primaryKey"`
	TaskID        int64  `gorm:"not null;index;uniqueIndex:task_result_position"`
	Position      int    `gorm:"not null;uniqueIndex:task_result_position"`
	Type          string `gorm:"size:16;not null"`
	Name          string `gorm:"size:255;not null"`
	URL           string `gorm:"type:text;not null"`
	RevisedPrompt string `gorm:"type:text;not null"`
	ContentType   string `gorm:"size:128;not null"`
	Size          int64  `gorm:"not null;default:0"`
}

func (TaskResult) TableName() string { return "task_results" }
