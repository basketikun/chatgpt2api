package handler

import (
	"time"
	"errors"
	"github.com/basketikun/chatgpt2api/internal/repository"
	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
	"net/http"
	"strconv"
)

type ConversationHandler struct{ service *service.ConversationService }

var conversationTypes = map[string]bool{"chat": true, "image": true, "speech": true, "transcription": true}

func NewConversationHandler(service *service.ConversationService) *ConversationHandler {
	return &ConversationHandler{service: service}
}

func (h *ConversationHandler) RegisterRoutes(router *gin.RouterGroup) {
	router.GET("/conversations", h.list)
	router.POST("/conversations", h.create)
	router.DELETE("/conversations", h.clear)
	router.GET("/conversations/:id", h.get)
	router.PATCH("/conversations/:id", h.update)
	router.DELETE("/conversations/:id", h.delete)
}

func (h *ConversationHandler) list(c *gin.Context) {
	conversationType := c.Query("type")
	if conversationType != "" && !conversationTypes[conversationType] {
		writeError(c, http.StatusUnprocessableEntity, errors.New("对话类型不正确"))
		return
	}
	items, err := h.service.List(c.Request.Context(), identity(c).ID, conversationType)
	if err != nil {
		writeError(c, http.StatusInternalServerError, err)
		return
	}
	result := make([]gin.H, 0, len(items))
	for _, item := range items {
		result = append(result, gin.H{"id": item.ID, "title": item.Title, "type": item.Type})
	}
	c.JSON(http.StatusOK, result)
}

func (h *ConversationHandler) create(c *gin.Context) {
	var body CreateConversationRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusUnprocessableEntity, errors.New("对话内容格式不正确"))
		return
	}
	if body.Title == nil || body.Type == nil || body.Model == nil || !conversationTypes[*body.Type] {
		writeError(c, http.StatusUnprocessableEntity, errors.New("对话内容格式不正确"))
		return
	}
	item, err := h.service.Create(c.Request.Context(), repository.Conversation{OwnerID: identity(c).ID, Title: *body.Title, Type: *body.Type, Model: *body.Model, Messages: body.Messages, Extra: body.Extra})
	writeResult(c, toConversationResponse(item), err)
}

func (h *ConversationHandler) get(c *gin.Context) {
	id, ok := conversationID(c)
	if !ok {
		return
	}
	item, err := h.service.Get(c.Request.Context(), identity(c).ID, id)
	if errors.Is(err, repository.ErrNotFound) {
		writeError(c, http.StatusNotFound, errors.New("这条对话不存在"))
		return
	}
	writeResult(c, toConversationResponse(item), err)
}

func (h *ConversationHandler) update(c *gin.Context) {
	var body UpdateConversationRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusUnprocessableEntity, errors.New("对话内容格式不正确"))
		return
	}
	if body.Type != nil && !conversationTypes[*body.Type] {
		writeError(c, http.StatusUnprocessableEntity, errors.New("对话类型不正确"))
		return
	}
	id, ok := conversationID(c)
	if !ok {
		return
	}
	item, err := h.service.Update(c.Request.Context(), identity(c).ID, id, service.ConversationPatch{Title: body.Title, Type: body.Type, Model: body.Model, Messages: body.Messages, Extra: body.Extra})
	if errors.Is(err, repository.ErrNotFound) {
		writeError(c, http.StatusNotFound, errors.New("conversation not found"))
		return
	}
	writeResult(c, toConversationResponse(item), err)
}

func (h *ConversationHandler) delete(c *gin.Context) {
	id, ok := conversationID(c)
	if !ok {
		return
	}
	removed, err := h.service.Delete(c.Request.Context(), identity(c).ID, id)
	if err != nil {
		writeError(c, http.StatusInternalServerError, err)
		return
	}
	if !removed {
		writeError(c, http.StatusNotFound, errors.New("conversation not found"))
		return
	}
	c.JSON(http.StatusOK, gin.H{"ok": true})
}

func (h *ConversationHandler) clear(c *gin.Context) {
	conversationType := c.Query("type")
	if conversationType != "" && !conversationTypes[conversationType] {
		writeError(c, http.StatusUnprocessableEntity, errors.New("对话类型不正确"))
		return
	}
	removed, err := h.service.Clear(c.Request.Context(), identity(c).ID, conversationType)
	writeResult(c, gin.H{"removed": removed}, err)
}
func conversationID(c *gin.Context) (int64, bool) {
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil {
		writeError(c, http.StatusUnprocessableEntity, errors.New("对话编号格式不正确"))
		return 0, false
	}
	return id, true
}
func toConversationResponse(item repository.Conversation) ConversationResponse {
	return ConversationResponse{ID: item.ID, Title: item.Title, Type: item.Type, Model: item.Model, Messages: item.Messages, Extra: item.Extra, CreatedAt: item.CreatedAt, UpdatedAt: item.UpdatedAt}
}

type ConversationResponse struct {
	ID        int64          `json:"id"`
	Title     string         `json:"title"`
	Type      string         `json:"type"`
	Model     string         `json:"model"`
	Messages  any            `json:"messages"`
	Extra     map[string]any `json:"extra"`
	CreatedAt time.Time      `json:"created_at"`
	UpdatedAt time.Time      `json:"updated_at"`
}
type CreateConversationRequest struct {
	Title    *string          `json:"title"`
	Type     *string          `json:"type"`
	Model    *string          `json:"model"`
	Messages []map[string]any `json:"messages"`
	Extra    map[string]any   `json:"extra"`
}
type UpdateConversationRequest struct {
	Title    *string        `json:"title"`
	Type     *string        `json:"type"`
	Model    *string        `json:"model"`
	Messages any            `json:"messages"`
	Extra    map[string]any `json:"extra"`
}
