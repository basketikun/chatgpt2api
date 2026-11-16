package upstream

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"strings"

	http "github.com/bogdanfinn/fhttp"
)

// ErrTokenInvalidated 表示上游返回 401，访问令牌已失效。
var ErrTokenInvalidated = errors.New("token invalidated")

type UpstreamHTTPError struct {
	Context    string
	StatusCode int
	Body       string
}

func (e *UpstreamHTTPError) Error() string {
	return fmt.Sprintf("%s failed: HTTP %d: %s", e.Context, e.StatusCode, e.Body)
}

func responseError(context string, response *http.Response) error {
	body, _ := io.ReadAll(response.Body)
	response.Body.Close()
	return &UpstreamHTTPError{Context: context, StatusCode: response.StatusCode, Body: string(body)}
}

// transientFragments match connection-level failures that are worth retrying.
// The upstream link (especially through a proxy egress) intermittently returns
// EOF / reset; a single retry nearly always succeeds, so these must not fail a
// task outright.
var transientFragments = []string{
	"eof",
	"connection reset",
	"connection refused",
	"connection aborted",
	"broken pipe",
	"i/o timeout",
	"tls handshake",
	"stream error",
	"unexpected eof",
	"no such host",
	"network is unreachable",
	"server closed idle connection",
	"http2: ",
}

// isTransientUpstreamError reports whether retrying the same request is
// likely to succeed.
func isTransientUpstreamError(err error) bool {
	if err == nil {
		return false
	}
	if errors.Is(err, io.EOF) || errors.Is(err, io.ErrUnexpectedEOF) || errors.Is(err, context.DeadlineExceeded) {
		return true
	}
	var netErr net.Error
	if errors.As(err, &netErr) {
		return true
	}
	var httpErr *UpstreamHTTPError
	if errors.As(err, &httpErr) {
		return httpErr.StatusCode == http.StatusTooManyRequests || httpErr.StatusCode >= 500
	}
	message := strings.ToLower(err.Error())
	for _, fragment := range transientFragments {
		if strings.Contains(message, fragment) {
			return true
		}
	}
	return false
}
