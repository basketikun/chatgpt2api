package repository

import (
	"context"
	"time"
)

type CallSample struct {
	Time       time.Time
	Status     string
	Model      string
	DurationMS float64
}

func (r *Repository) CallSamples(ctx context.Context, start time.Time, end time.Time) ([]CallSample, error) {
	query := r.db.WithContext(ctx).Model(&Log{}).Select("time", "status", "model", "duration_ms").Where("status IN ?", []string{"success", "failed", "running"})
	if r.db.Dialector.Name() == "sqlite" {
		query = query.Where("julianday(time) >= julianday(?) AND julianday(time) < julianday(?)", start, end)
	} else {
		query = query.Where("time >= ? AND time < ?", start, end)
	}
	items := []CallSample{}
	err := query.Find(&items).Error
	return items, err
}
