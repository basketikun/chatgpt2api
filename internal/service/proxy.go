package service

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/basketikun/chatgpt2api/internal/config"
	fhttp "github.com/bogdanfinn/fhttp"
	tls_client "github.com/bogdanfinn/tls-client"
	"github.com/bogdanfinn/tls-client/profiles"
	netproxy "golang.org/x/net/proxy"
)

type Clearance struct {
	Cookies   map[string]string
	UserAgent string
	ExpiresAt time.Time
}

type ProxyService struct {
	config    *config.Config
	mu        sync.RWMutex
	clearance map[string]Clearance
	clientMu  sync.Mutex
	clients   map[string]*http.Client
	tlsClient map[string]tls_client.HttpClient
}

func NewProxyService(config *config.Config) *ProxyService {
	return &ProxyService{config: config, clearance: map[string]Clearance{}, clients: map[string]*http.Client{}, tlsClient: map[string]tls_client.HttpClient{}}
}

func (s *ProxyService) Client(accountProxy string, resource bool, upstream bool) *http.Client {
	proxyURL, _ := s.proxy(accountProxy, resource, upstream)
	s.clientMu.Lock()
	defer s.clientMu.Unlock()
	if client := s.clients[proxyURL]; client != nil {
		return client
	}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	if proxyURL != "" {
		parsed, err := url.Parse(normalizeProxyURL(proxyURL))
		if err == nil && (parsed.Scheme == "socks5" || parsed.Scheme == "socks5h") {
			var auth *netproxy.Auth
			if parsed.User != nil {
				password, _ := parsed.User.Password()
				auth = &netproxy.Auth{User: parsed.User.Username(), Password: password}
			}
			if dialer, err := netproxy.SOCKS5("tcp", parsed.Host, auth, netproxy.Direct); err == nil {
				transport.DialContext = func(_ context.Context, network string, address string) (net.Conn, error) {
					return dialer.Dial(network, address)
				}
			}
		} else if err == nil {
			transport.Proxy = http.ProxyURL(parsed)
		}
	}
	client := &http.Client{Transport: transport, Timeout: 300 * time.Second}
	s.clients[proxyURL] = client
	return client
}

func (s *ProxyService) TLSClient(accountProxy string, resource bool, timeoutSeconds ...int) (tls_client.HttpClient, error) {
	proxyURL, _ := s.proxy(accountProxy, resource, true)
	timeout := 300
	if len(timeoutSeconds) > 0 {
		timeout = timeoutSeconds[0]
	}
	key := proxyURL + "|" + strconv.Itoa(timeout)
	s.clientMu.Lock()
	defer s.clientMu.Unlock()
	if client := s.tlsClient[key]; client != nil {
		return client, nil
	}
	options := []tls_client.HttpClientOption{tls_client.WithTimeoutSeconds(timeout), tls_client.WithClientProfile(profiles.Chrome_146), tls_client.WithRandomTLSExtensionOrder()}
	if proxyURL != "" {
		options = append(options, tls_client.WithProxyUrl(normalizeProxyURL(proxyURL)))
	}
	client, err := tls_client.NewHttpClient(tls_client.NewNoopLogger(), options...)
	if err == nil {
		s.tlsClient[key] = client
	}
	return client, err
}

func (s *ProxyService) UpstreamClearance(ctx context.Context, targetURL string) (string, map[string]string) {
	if !s.config.ProxyRuntime.Enabled || s.config.ProxyRuntime.Clearance.Mode == "none" {
		return "", nil
	}
	bundle := s.CachedClearance("chatgpt.com")
	if time.Now().After(bundle.ExpiresAt) {
		bundle, _ = s.RefreshClearance(ctx, targetURL)
	}
	return bundle.UserAgent, bundle.Cookies
}

func (s *ProxyService) RefreshClearance(ctx context.Context, targetURL string) (Clearance, error) {
	settings := s.config.ProxyRuntime.Clearance
	if !s.config.ProxyRuntime.Enabled || settings.Mode == "none" {
		return Clearance{}, errors.New("clearance is disabled")
	}
	parsed, err := url.Parse(targetURL)
	if err != nil {
		return Clearance{}, err
	}
	if settings.Mode == "manual" {
		cookies := parseCookies(settings.CFCookies)
		if settings.CFClearance != "" {
			cookies["cf_clearance"] = settings.CFClearance
		}
		bundle := Clearance{Cookies: cookies, UserAgent: settings.UserAgent, ExpiresAt: time.Now().Add(time.Duration(settings.RefreshInterval) * time.Second)}
		s.mu.Lock()
		s.clearance[parsed.Hostname()] = bundle
		s.mu.Unlock()
		return bundle, nil
	}
	payload, _ := json.Marshal(map[string]any{"cmd": "request.get", "url": targetURL, "maxTimeout": settings.TimeoutSeconds * 1000, "proxy": map[string]string{"url": s.config.ProxyRuntime.ProxyURL}})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, settings.FlareSolverrURL+"/v1", strings.NewReader(string(payload)))
	if err != nil {
		return Clearance{}, err
	}
	req.Header.Set("Content-Type", "application/json")
	response, err := s.Client("", false, false).Do(req)
	if err != nil {
		return Clearance{}, err
	}
	defer response.Body.Close()
	var result struct {
		Status   string `json:"status"`
		Solution struct {
			UserAgent string `json:"userAgent"`
			Cookies   []struct {
				Name   string `json:"name"`
				Value  string `json:"value"`
				Domain string `json:"domain"`
			} `json:"cookies"`
		} `json:"solution"`
	}
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		return Clearance{}, err
	}
	if result.Status != "ok" {
		return Clearance{}, errors.New("clearance refresh returned no bundle")
	}
	cookies := map[string]string{}
	for _, item := range result.Solution.Cookies {
		if item.Domain == "" || parsed.Hostname() == strings.TrimPrefix(item.Domain, ".") || strings.HasSuffix(parsed.Hostname(), item.Domain) {
			cookies[item.Name] = item.Value
		}
	}
	bundle := Clearance{Cookies: cookies, UserAgent: result.Solution.UserAgent, ExpiresAt: time.Now().Add(time.Duration(settings.RefreshInterval) * time.Second)}
	s.mu.Lock()
	s.clearance[parsed.Hostname()] = bundle
	s.mu.Unlock()
	return bundle, nil
}

func (s *ProxyService) CachedClearance(host string) Clearance {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.clearance[host]
}

func (s *ProxyService) Status() map[string]any {
	s.mu.RLock()
	hosts := make([]string, 0, len(s.clearance))
	for host := range s.clearance {
		hosts = append(hosts, host)
	}
	s.mu.RUnlock()
	runtime := s.config.ProxyRuntime
	proxyURL, proxySource := s.proxy("", false, true)
	return map[string]any{"enabled": runtime.Enabled, "egress_mode": runtime.EgressMode, "proxy_source": proxySource, "has_proxy": proxyURL != "", "clearance_enabled": runtime.Enabled && runtime.Clearance.Mode != "none", "clearance_mode": runtime.Clearance.Mode, "has_clearance_bundle": len(hosts) > 0, "cached_clearance_hosts": hosts}
}

func (s *ProxyService) Test(ctx context.Context, proxyURL string) map[string]any {
	started := time.Now()
	proxySource := "input"
	if proxyURL == "" {
		proxyURL, proxySource = s.proxy("", false, true)
	}
	client, err := s.TLSClient(proxyURL, false)
	if err != nil {
		return map[string]any{"ok": false, "status": 0, "latency_ms": time.Since(started).Milliseconds(), "error": redactProxyCredentials(err.Error()), "proxy_source": proxySource, "has_proxy": proxyURL != ""}
	}
	req, err := fhttp.NewRequestWithContext(ctx, fhttp.MethodGet, "https://chatgpt.com/api/auth/csrf", nil)
	if err != nil {
		return map[string]any{"ok": false, "status": 0, "latency_ms": time.Since(started).Milliseconds(), "error": redactProxyCredentials(err.Error()), "proxy_source": proxySource, "has_proxy": proxyURL != ""}
	}
	response, err := client.Do(req)
	latency := time.Since(started).Milliseconds()
	if err != nil {
		return map[string]any{"ok": false, "status": 0, "latency_ms": latency, "error": redactProxyCredentials(err.Error()), "proxy_source": proxySource, "has_proxy": proxyURL != ""}
	}
	defer response.Body.Close()
	return map[string]any{"ok": response.StatusCode < 500, "status": response.StatusCode, "latency_ms": latency, "error": nil, "proxy_source": proxySource, "has_proxy": proxyURL != ""}
}

func (s *ProxyService) proxy(accountProxy string, resource bool, upstream bool) (string, string) {
	if accountProxy != "" {
		return normalizeProxyURL(accountProxy), "account"
	}
	if upstream && s.config.ProxyRuntime.Enabled && s.config.ProxyRuntime.EgressMode == "single_proxy" {
		if resource && s.config.ProxyRuntime.ResourceProxyURL != "" {
			return normalizeProxyURL(s.config.ProxyRuntime.ResourceProxyURL), "runtime_resource"
		}
		if s.config.ProxyRuntime.ProxyURL != "" {
			return normalizeProxyURL(s.config.ProxyRuntime.ProxyURL), "runtime"
		}
	}
	if s.config.Proxy != "" {
		return normalizeProxyURL(s.config.Proxy), "global"
	}
	return "", "direct"
}

var proxyCredentials = regexp.MustCompile(`(?i)((?:https?|socks5h?|socks)://)[^\s/@:]+:[^\s/@]+@`)

func redactProxyCredentials(value string) string {
	return proxyCredentials.ReplaceAllString(value, `${1}[REDACTED]@`)
}

func normalizeProxyURL(value string) string {
	if !strings.Contains(value, "://") {
		value = "http://" + value
	}
	if strings.HasPrefix(value, "socks://") {
		return "socks5h://" + strings.TrimPrefix(value, "socks://")
	}
	if strings.HasPrefix(value, "socks5://") {
		return "socks5h://" + strings.TrimPrefix(value, "socks5://")
	}
	return value
}

func parseCookies(value string) map[string]string {
	result := map[string]string{}
	for _, item := range strings.Split(value, ";") {
		name, content, ok := strings.Cut(item, "=")
		if ok {
			result[name] = content
		}
	}
	return result
}
