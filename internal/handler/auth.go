package handler

import (
	"time"
	"errors"
	"strings"
	"github.com/basketikun/chatgpt2api/internal/repository"
	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
	"net/http"
)

type AuthHandler struct {
	service *service.AuthService
	version string
}

func NewAuthHandler(service *service.AuthService, version string) *AuthHandler {
	return &AuthHandler{service: service, version: version}
}

func (h *AuthHandler) RegisterLogin(router *gin.Engine) { router.POST("/auth/login", h.login) }

func (h *AuthHandler) RegisterRoutes(router *gin.RouterGroup) {
	router.GET("/auth/users", h.list)
	router.POST("/auth/users", h.create)
	router.POST("/auth/users/:keyID", h.update)
	router.DELETE("/auth/users/:keyID", h.delete)
}

func (h *AuthHandler) login(c *gin.Context) {
	identity, err := h.service.Authenticate(c.Request.Context(), c.GetHeader("Authorization"), true)
	if err != nil {
		writeError(c, http.StatusUnauthorized, service.ErrUnauthorized)
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true, "version": h.version, "role": identity.Role, "subject_id": identity.ID, "name": identity.Name})
}

func (h *AuthHandler) list(c *gin.Context) {
	items, err := h.service.List(c.Request.Context())
	writeResult(c, gin.H{"items": toAPIKeyResponses(items)}, err)
}

func (h *AuthHandler) create(c *gin.Context) {
	var body CreateAPIKeyRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, errors.New("请输入新的专用密钥"))
		return
	}
	item, err := h.service.Create(c.Request.Context(), body.Name, body.Key, body.Plan, body.Route)
	if err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	items, err := h.service.List(c.Request.Context())
	writeResult(c, gin.H{"item": toAPIKeyResponse(item), "items": toAPIKeyResponses(items)}, err)
}

func (h *AuthHandler) update(c *gin.Context) {
	var body UpdateAPIKeyRequest
	if err := c.ShouldBindJSON(&body); err != nil || body.Name == nil && body.Enabled == nil && body.Key == nil && len(body.Plan) == 0 && len(body.Route) == 0 {
		writeError(c, http.StatusBadRequest, errors.New("还没有检测到改动，请修改后再保存"))
		return
	}
	item, err := h.service.Update(c.Request.Context(), c.Param("keyID"), body.Name, body.Enabled, body.Key, body.Plan, body.Route)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(c, http.StatusNotFound, errors.New("这条用户密钥不存在，可能已经被删除"))
		return
	}
	if err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	items, err := h.service.List(c.Request.Context())
	writeResult(c, gin.H{"item": toAPIKeyResponse(item), "items": toAPIKeyResponses(items)}, err)
}

func (h *AuthHandler) delete(c *gin.Context) {
	err := h.service.Delete(c.Request.Context(), c.Param("keyID"))
	if errors.Is(err, repository.ErrNotFound) {
		writeError(c, http.StatusNotFound, errors.New("这条用户密钥不存在，可能已经被删除"))
		return
	}
	items, listErr := h.service.List(c.Request.Context())
	if err == nil {
		err = listErr
	}
	writeResult(c, gin.H{"items": toAPIKeyResponses(items)}, err)
}

func toAPIKeyResponse(item repository.APIKey) APIKeyResponse {
	return APIKeyResponse{ID: item.ID, Name: item.Name, Role: item.Role, Key: item.Key, Plan: strings.Split(item.Plan, ","), Route: strings.Split(item.Route, ","), Enabled: item.Enabled, CreatedAt: item.CreatedAt, LastUsedAt: item.LastUsedAt}
}

func toAPIKeyResponses(items []repository.APIKey) []APIKeyResponse {
	result := make([]APIKeyResponse, 0, len(items))
	for _, item := range items {
		result = append(result, toAPIKeyResponse(item))
	}
	return result
}

type APIKeyResponse struct {
	ID         string     `json:"id"`
	Name       string     `json:"name"`
	Role       string     `json:"role"`
	Key        string     `json:"key"`
	Plan       []string   `json:"plan"`
	Route      []string   `json:"route"`
	Enabled    bool       `json:"enabled"`
	CreatedAt  time.Time  `json:"created_at"`
	LastUsedAt *time.Time `json:"last_used_at"`
}
type CreateAPIKeyRequest struct {
	Name  string `json:"name"`
	Key   string `json:"key" binding:"required"`
	Plan  []string `json:"plan" binding:"required,min=1,dive,oneof=free plus team pro"`
	Route []string `json:"route" binding:"required,min=1,dive,oneof=web codex"`
}
type UpdateAPIKeyRequest struct {
	Name    *string `json:"name"`
	Enabled *bool   `json:"enabled"`
	Key     *string `json:"key"`
	Plan    []string `json:"plan" binding:"omitempty,dive,oneof=free plus team pro"`
	Route   []string `json:"route" binding:"omitempty,dive,oneof=web codex"`
}
