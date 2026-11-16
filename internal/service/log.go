package service

import (
	"context"
	"sync"
	"time"

	"github.com/basketikun/chatgpt2api/internal/repository"
	"github.com/google/uuid"
)

type LogService struct{ repo *repository.Repository }
type CallLog struct {
	service  *LogService
	identity Identity
	id       string
	summary  string
	started  time.Time
	detail   map[string]any
	events   []map[string]any
	finished bool
	mu       sync.Mutex
}

func NewLogService(repo *repository.Repository) *LogService { return &LogService{repo: repo} }
func (s *LogService) List(ctx context.Context, startDate string, endDate string, page int, pageSize int) ([]repository.Log, int64, error) {
	return s.repo.Logs(ctx, startDate, endDate, page, pageSize)
}

func (s *LogService) Create(ctx context.Context, summary string, detail map[string]any) (repository.Log, error) {
	item := repository.Log{ID: uuid.NewString()[:32], Time: time.Now(), Summary: summary, Detail: detail}
	return item, s.repo.SaveLog(ctx, item)
}

func (s *LogService) NewCallLog(identity Identity, endpoint string, model string, summary string, requestText string, started time.Time) *CallLog {
	if started.IsZero() {
		started = time.Now()
	}
	stamp := started.Format("2006-01-02 15:04:05")
	events := []map[string]any{{"time": stamp, "elapsed_ms": int64(0), "message": "调用已接收"}}
	detail := map[string]any{"key_id": identity.ID, "key_name": identity.Name, "role": identity.Role, "endpoint": endpoint, "model": model, "started_at": stamp, "updated_at": stamp, "duration_ms": int64(0), "status": "running", "stage": "调用已接收", "events": events}
	if requestText != "" {
		value := []rune(requestText)
		if len(value) > 1000 {
			requestText = string(value[:999]) + "…"
		}
		detail["request_text"] = requestText
	}
	call := &CallLog{service: s, identity: identity, summary: summary, started: started, detail: detail, events: events}
	item, err := s.Create(context.Background(), summary+"调用已接收", detail)
	if err == nil {
		call.id = item.ID
	}
	return call
}

func (l *CallLog) Add(message string, detail map[string]any) {
	if l == nil {
		return
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.finished {
		return
	}
	now := time.Now()
	event := map[string]any{"time": now.Format("2006-01-02 15:04:05"), "elapsed_ms": time.Since(l.started).Milliseconds(), "message": message}
	if len(detail) > 0 {
		event["detail"] = detail
	}
	l.events = append(l.events, event)
	l.detail["updated_at"], l.detail["duration_ms"], l.detail["stage"], l.detail["events"] = event["time"], event["elapsed_ms"], message, l.events
	l.persist(l.summary + message)
}

func (l *CallLog) Update(detail map[string]any) {
	if l == nil {
		return
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.finished {
		return
	}
	for key, value := range detail {
		l.detail[key] = value
	}
	l.detail["updated_at"], l.detail["duration_ms"] = time.Now().Format("2006-01-02 15:04:05"), time.Since(l.started).Milliseconds()
}

func (l *CallLog) Save(suffix string, status string, detail map[string]any) {
	if l == nil {
		return
	}
	l.mu.Lock()
	defer l.mu.Unlock()
	if l.finished {
		return
	}
	l.finished = true
	for key, value := range detail {
		l.detail[key] = value
	}
	now := time.Now()
	event := map[string]any{"time": now.Format("2006-01-02 15:04:05"), "elapsed_ms": time.Since(l.started).Milliseconds(), "message": suffix}
	l.events = append(l.events, event)
	l.detail["ended_at"], l.detail["updated_at"], l.detail["duration_ms"], l.detail["status"], l.detail["stage"], l.detail["events"] = event["time"], event["time"], event["elapsed_ms"], status, suffix, l.events
	l.persist(l.summary + suffix)
}

func (l *CallLog) persist(summary string) {
	if l.id != "" {
		l.service.repo.UpdateLog(context.Background(), l.id, summary, l.detail)
	}
}

func (s *LogService) Delete(ctx context.Context, ids []string) (int64, error) {
	return s.repo.DeleteLogs(ctx, ids)
}

func (s *LogService) CleanupExpired(ctx context.Context, cutoff time.Time) error {
	return s.repo.DeleteLogsBefore(ctx, cutoff)
}
