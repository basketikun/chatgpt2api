package service

import (
	"context"
	"sort"
	"sync"
	"time"

	"github.com/basketikun/chatgpt2api/internal/repository"
)

type OverviewService struct {
	repo     *repository.Repository
	callsMu  sync.Mutex
	calls    map[string]CallOverview
	systemMu sync.Mutex
	system   *SystemOverview
}

type CallCounts struct {
	Total             int      `json:"total"`
	Success           int      `json:"success"`
	Failed            int      `json:"failed"`
	Running           int      `json:"running"`
	SuccessRate       *float64 `json:"success_rate"`
	AverageDurationMS *float64 `json:"average_duration_ms"`
	durationMS        float64
}

type CallBucket struct {
	Time time.Time `json:"time"`
	CallCounts
}

type ModelCalls struct {
	Model string `json:"model"`
	CallCounts
}

type CallOverview struct {
	SampledAt time.Time    `json:"sampled_at"`
	Start     time.Time    `json:"start"`
	End       time.Time    `json:"end"`
	Summary   CallCounts   `json:"summary"`
	Trend     []CallBucket `json:"trend"`
	Models    []ModelCalls `json:"models"`
}

func NewOverviewService(repo *repository.Repository) *OverviewService {
	return &OverviewService{repo: repo, calls: map[string]CallOverview{}}
}

func (counts *CallCounts) Add(sample repository.CallSample) {
	counts.Total++
	switch sample.Status {
	case "success":
		counts.Success++
		counts.durationMS += sample.DurationMS
	case "failed":
		counts.Failed++
		counts.durationMS += sample.DurationMS
	case "running":
		counts.Running++
	}
	completed := counts.Success + counts.Failed
	if completed > 0 {
		rate := float64(counts.Success) * 100 / float64(completed)
		average := counts.durationMS / float64(completed)
		counts.SuccessRate, counts.AverageDurationMS = &rate, &average
	}
}

func (s *OverviewService) Calls(ctx context.Context, period string) (CallOverview, error) {
	s.callsMu.Lock()
	defer s.callsMu.Unlock()
	if cached, ok := s.calls[period]; ok && time.Since(cached.SampledAt) < 30*time.Second {
		return cached, nil
	}
	window, step := 24*time.Hour, time.Hour
	if period == "7d" {
		window, step = 7*24*time.Hour, 6*time.Hour
	}
	now := time.Now()
	result := CallOverview{SampledAt: now, Start: now.Add(-window), End: now, Trend: make([]CallBucket, int(window/step)), Models: []ModelCalls{}}
	for index := range result.Trend {
		result.Trend[index].Time = result.Start.Add(time.Duration(index) * step)
	}
	samples, err := s.repo.CallSamples(ctx, result.Start, result.End)
	if err != nil {
		return result, err
	}
	models := map[string]*ModelCalls{}
	for _, sample := range samples {
		result.Summary.Add(sample)
		index := int(sample.Time.Sub(result.Start) / step)
		result.Trend[index].Add(sample)
		if models[sample.Model] == nil {
			models[sample.Model] = &ModelCalls{Model: sample.Model}
		}
		models[sample.Model].Add(sample)
	}
	for _, model := range models {
		result.Models = append(result.Models, *model)
	}
	sort.Slice(result.Models, func(i, j int) bool {
		if result.Models[i].Total == result.Models[j].Total {
			return result.Models[i].Model < result.Models[j].Model
		}
		return result.Models[i].Total > result.Models[j].Total
	})
	s.calls[period] = result
	return result, nil
}
