package upstream

import (
	"context"
	"time"
)

// retryTransient re-runs fn until it succeeds, giving up when the failure is not
// transient or the wall clock budget is exhausted. The upstream link drops in
// bursts that can outlast a fixed attempt count, so callers budget by time.
func retryTransient(ctx context.Context, budget time.Duration, fn func() error) error {
	deadline := time.Now().Add(budget)
	for attempt := 0; ; attempt++ {
		err := fn()
		if err == nil {
			return nil
		}
		if !isTransientUpstreamError(err) || time.Now().After(deadline) {
			return err
		}
		delay := upstreamRetryBaseDelay * time.Duration(attempt+1)
		if delay > time.Duration(upstreamRetryMaxDelaySeconds*float64(time.Second)) {
			delay = time.Duration(upstreamRetryMaxDelaySeconds * float64(time.Second))
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(delay):
		}
	}
}
