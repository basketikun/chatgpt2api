package service

import (
	"context"
	"crypto/subtle"
	"errors"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/basketikun/chatgpt2api/internal/repository"
	"github.com/google/uuid"
)

var ErrUnauthorized = errors.New("密钥无效或已失效，请重新登录")

type Identity struct {
	ID    string
	Name  string
	Role  string
	Plans  []string
	Routes []string
}

type AuthService struct {
	repo     *repository.Repository
	adminKey string
	mu       sync.RWMutex
	keys     map[string]cachedKey
}

type cachedKey struct {
	item      repository.APIKey
	expiresAt time.Time
}

func NewAuthService(repo *repository.Repository, adminKey string) *AuthService {
	return &AuthService{repo: repo, adminKey: adminKey, keys: map[string]cachedKey{}}
}

func (s *AuthService) apiKey(ctx context.Context, key string) (repository.APIKey, error) {
	s.mu.RLock()
	cached, ok := s.keys[key]
	s.mu.RUnlock()
	if ok && time.Now().Before(cached.expiresAt) {
		return cached.item, nil
	}
	item, err := s.repo.APIKeyByValue(ctx, key)
	if err != nil {
		return item, err
	}
	s.mu.Lock()
	s.keys[key] = cachedKey{item: item, expiresAt: time.Now().Add(30 * time.Second)}
	s.mu.Unlock()
	return item, nil
}

func (s *AuthService) clearKeys() {
	s.mu.Lock()
	clear(s.keys)
	s.mu.Unlock()
}

func (s *AuthService) Authenticate(ctx context.Context, authorization string, touch bool) (Identity, error) {
	scheme, key, ok := strings.Cut(authorization, " ")
	if !ok || !strings.EqualFold(scheme, "bearer") || key == "" {
		return Identity{}, ErrUnauthorized
	}
	if subtle.ConstantTimeCompare([]byte(key), []byte(s.adminKey)) == 1 {
		return Identity{ID: "admin", Name: "管理员", Role: "admin", Routes: []string{"web"}}, nil
	}
	item, err := s.apiKey(ctx, key)
	if errors.Is(err, repository.ErrNotFound) {
		return Identity{}, ErrUnauthorized
	}
	if err != nil {
		return Identity{}, err
	}
	if touch {
		if err := s.repo.TouchAPIKey(ctx, item.ID, time.Now().UTC()); err != nil {
			return Identity{}, err
		}
	}
	return Identity{ID: item.ID, Name: item.Name, Role: item.Role, Plans: strings.Split(item.Plan, ","), Routes: strings.Split(item.Route, ",")}, nil
}

func (s *AuthService) List(ctx context.Context) ([]repository.APIKey, error) {
	return s.repo.APIKeys(ctx, "user")
}

func (s *AuthService) Create(ctx context.Context, name string, key string, plan []string, route []string) (repository.APIKey, error) {
	if key == "" {
		return repository.APIKey{}, errors.New("请输入新的专用密钥")
	}
	if key == s.adminKey {
		return repository.APIKey{}, errors.New("这个密钥和管理员密钥冲突了，请换一个新的密钥")
	}
	exists, err := s.repo.APIKeyExists(ctx, key, "")
	if err != nil {
		return repository.APIKey{}, err
	}
	if exists {
		return repository.APIKey{}, errors.New("这个专用密钥已经存在，请换一个新的密钥")
	}
	name, err = s.availableName(ctx, name, "")
	if err != nil {
		return repository.APIKey{}, err
	}
	item := repository.APIKey{ID: strings.ReplaceAll(uuid.NewString(), "-", ""), Name: name, Role: "user", Key: key, Plan: strings.Join(plan, ","), Route: strings.Join(route, ","), Enabled: true, CreatedAt: time.Now().UTC()}
	return item, s.repo.SaveAPIKey(ctx, item)
}

func (s *AuthService) Update(ctx context.Context, id string, name *string, enabled *bool, key *string, plan []string, route []string) (repository.APIKey, error) {
	item, err := s.repo.APIKeyByID(ctx, id)
	if err != nil {
		return repository.APIKey{}, err
	}
	if item.Role != "user" {
		return repository.APIKey{}, repository.ErrNotFound
	}
	if name != nil {
		item.Name, err = s.availableName(ctx, *name, id)
		if err != nil {
			return repository.APIKey{}, err
		}
	}
	if key != nil {
		if *key == "" || *key == s.adminKey {
			return repository.APIKey{}, errors.New("请输入与管理员密钥不同的新密钥")
		}
		exists, err := s.repo.APIKeyExists(ctx, *key, id)
		if err != nil {
			return repository.APIKey{}, err
		}
		if exists {
			return repository.APIKey{}, errors.New("这个专用密钥已经存在，请换一个新的密钥")
		}
		item.Key = *key
	}
	if enabled != nil {
		item.Enabled = *enabled
	}
	if len(plan) > 0 {
		item.Plan = strings.Join(plan, ",")
	}
	if len(route) > 0 {
		item.Route = strings.Join(route, ",")
	}
	err = s.repo.SaveAPIKey(ctx, item)
	s.clearKeys()
	return item, err
}

func (s *AuthService) Delete(ctx context.Context, id string) error {
	item, err := s.repo.APIKeyByID(ctx, id)
	if err != nil {
		return err
	}
	if item.Role != "user" {
		return repository.ErrNotFound
	}
	err = s.repo.DeleteAPIKey(ctx, id)
	s.clearKeys()
	return err
}

func (s *AuthService) availableName(ctx context.Context, name string, excludeID string) (string, error) {
	if name != "" {
		exists, err := s.repo.APIKeyNameExists(ctx, name, "user", excludeID)
		if err != nil {
			return "", err
		}
		if exists {
			return "", errors.New("这个名称已经在使用中了，换一个更容易区分的名称吧")
		}
		return name, nil
	}
	name = "普通用户"
	for suffix := 2; ; suffix++ {
		exists, err := s.repo.APIKeyNameExists(ctx, name, "user", excludeID)
		if err != nil || !exists {
			return name, err
		}
		name = "普通用户 " + strconv.Itoa(suffix)
	}
}
