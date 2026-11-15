package service

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
)

const (
	openAIAuthBase         = "https://auth.openai.com"
	openAIPlatformBase     = "https://platform.openai.com"
	openAIPlatformClientID = "app_2SKx67EdpoN0G6j64rFvigXD"
	openAIRedirectURI      = "https://platform.openai.com/auth/callback"
	openAIAudience         = "https://api.openai.com/v1"
	openAIAuth0Client      = "eyJuYW1lIjoiYXV0aDAtc3BhLWpzIiwidmVyc2lvbiI6IjEuMjEuMCJ9"
	openAIUserAgent        = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
	oauthMaxSessions       = 64
)

type oauthSession struct {
	Verifier  string
	State     string
	CreatedAt time.Time
}
type OAuthService struct {
	proxy    *ProxyService
	mu       sync.Mutex
	sessions map[string]oauthSession
}

func NewOAuthService(proxy *ProxyService) *OAuthService {
	return &OAuthService{proxy: proxy, sessions: map[string]oauthSession{}}
}

func (s *OAuthService) Start(email string) map[string]string {
	verifier := randomURLSafe(64)
	challengeHash := sha256.Sum256([]byte(verifier))
	challenge := base64.RawURLEncoding.EncodeToString(challengeHash[:])
	id := strings.ReplaceAll(uuid.NewString(), "-", "")
	state := id + "." + randomURLSafe(16)
	params := url.Values{"issuer": {openAIAuthBase}, "client_id": {openAIPlatformClientID}, "audience": {openAIAudience}, "redirect_uri": {openAIRedirectURI}, "device_id": {uuid.NewString()}, "screen_hint": {"login_or_signup"}, "max_age": {"0"}, "scope": {"openid profile email offline_access"}, "response_type": {"code"}, "response_mode": {"query"}, "state": {state}, "nonce": {randomURLSafe(32)}, "code_challenge": {challenge}, "code_challenge_method": {"S256"}, "auth0Client": {openAIAuth0Client}}
	if email != "" {
		params.Set("login_hint", email)
	}
	s.mu.Lock()
	s.sessions[id] = oauthSession{Verifier: verifier, State: state, CreatedAt: time.Now()}
	s.purge()
	s.mu.Unlock()
	return map[string]string{"session_id": id, "authorize_url": openAIAuthBase + "/api/accounts/authorize?" + params.Encode(), "expires_in": "600", "redirect_uri_prefix": openAIRedirectURI}
}

func (s *OAuthService) Finish(ctx context.Context, sessionID string, callback string) (map[string]string, error) {
	code, state := callback, ""
	if strings.HasPrefix(callback, "http://") || strings.HasPrefix(callback, "https://") {
		parsed, err := url.Parse(callback)
		if err != nil {
			return nil, err
		}
		code, state = parsed.Query().Get("code"), parsed.Query().Get("state")
		if code == "" {
			detail := parsed.Query().Get("error_description")
			if detail == "" {
				detail = parsed.Query().Get("error")
			}
			if detail != "" {
				return nil, errors.New(detail)
			}
		}
	}
	if code == "" {
		return nil, errors.New("缺少 code 或 callback URL")
	}
	if state != "" {
		stateID, _, _ := strings.Cut(state, ".")
		if stateID != "" {
			sessionID = stateID
		}
	}
	s.mu.Lock()
	s.purge()
	session, ok := s.sessions[sessionID]
	s.mu.Unlock()
	if !ok {
		return nil, errors.New("OAuth 会话已过期或不存在，请重新生成")
	}
	if state != "" && state != session.State {
		return nil, errors.New("state 不匹配，请重新生成后重试")
	}
	payload, _ := json.Marshal(map[string]string{"client_id": openAIPlatformClientID, "code_verifier": session.Verifier, "grant_type": "authorization_code", "code": code, "redirect_uri": openAIRedirectURI})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, openAIAuthBase+"/api/accounts/oauth/token", strings.NewReader(string(payload)))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", openAIUserAgent)
	req.Header.Set("Origin", openAIPlatformBase)
	req.Header.Set("Referer", openAIPlatformBase+"/")
	response, err := s.proxy.Client("", false, false).Do(req)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		return nil, err
	}
	var result map[string]any
	json.Unmarshal(body, &result)
	access, _ := result["access_token"].(string)
	refresh, _ := result["refresh_token"].(string)
	idToken, _ := result["id_token"].(string)
	if response.StatusCode == http.StatusOK && access != "" && refresh == "" {
		return nil, errors.New("OpenAI 没有返回 refresh_token")
	}
	if response.StatusCode != http.StatusOK || access == "" {
		detail, _ := result["error_description"].(string)
		if detail == "" {
			detail, _ = result["error"].(string)
		}
		if detail == "" {
			detail, _ = result["message"].(string)
		}
		if detail == "" {
			detail = string(body)
		}
		if len(detail) > 300 {
			detail = detail[:300]
		}
		return nil, fmt.Errorf("OpenAI 拒绝换 Token (HTTP %d): %s", response.StatusCode, detail)
	}
	s.mu.Lock()
	delete(s.sessions, sessionID)
	s.mu.Unlock()
	return map[string]string{"access_token": access, "refresh_token": refresh, "id_token": idToken}, nil
}

func (s *OAuthService) purge() {
	now := time.Now()
	for id, session := range s.sessions {
		if now.Sub(session.CreatedAt) > 10*time.Minute {
			delete(s.sessions, id)
		}
	}
	for len(s.sessions) > oauthMaxSessions {
		oldestID := ""
		var oldest time.Time
		for id, session := range s.sessions {
			if oldestID == "" || session.CreatedAt.Before(oldest) {
				oldestID, oldest = id, session.CreatedAt
			}
		}
		delete(s.sessions, oldestID)
	}
}
func randomURLSafe(size int) string {
	data := make([]byte, size)
	rand.Read(data)
	return base64.RawURLEncoding.EncodeToString(data)
}
