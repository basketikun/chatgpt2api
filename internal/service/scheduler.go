package service

import (
	"context"
	"time"

	"github.com/basketikun/chatgpt2api/internal/config"
)

type Scheduler struct {
	accounts *AccountService
	images   *ImageService
	tasks    *TaskService
	logs     *LogService
	config   *config.Config
}

func NewScheduler(accounts *AccountService, images *ImageService, tasks *TaskService, logs *LogService, config *config.Config) *Scheduler {
	return &Scheduler{accounts: accounts, images: images, tasks: tasks, logs: logs, config: config}
}
func (s *Scheduler) Run(ctx context.Context) { go s.refreshAccounts(ctx); go s.cleanupImages(ctx) }
func (s *Scheduler) refreshAccounts(ctx context.Context) {
	ticker := time.NewTicker(time.Duration(s.config.Account.RefreshIntervalMinute) * time.Minute)
	defer ticker.Stop()
	for {
		s.accounts.RefreshScheduled(ctx)
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
func (s *Scheduler) cleanupImages(ctx context.Context) {
	ticker := time.NewTicker(30 * time.Minute)
	defer ticker.Stop()
	for {
		s.images.CleanupExpired(ctx)
		s.images.Cleanup(ctx, int64(s.config.Image.MinFreeMB), false)
		s.tasks.CleanupExpired(ctx)
		s.logs.CleanupExpired(ctx, time.Now().AddDate(0, 0, -s.config.Image.RetentionDays))
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}
