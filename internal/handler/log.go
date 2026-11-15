package handler

import (
	"time"
	"github.com/basketikun/chatgpt2api/internal/repository"
	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
	"net/http"
)

type LogHandler struct{ service *service.LogService }

func NewLogHandler(service *service.LogService) *LogHandler { return &LogHandler{service: service} }
func (h *LogHandler) RegisterRoutes(router *gin.RouterGroup) {
	router.GET("/logs", h.list)
	router.POST("/logs/delete", h.deleteMany)
}
func (h *LogHandler) list(c *gin.Context) {
	page, size := intQuery(c.Query("page"), 1), intQuery(c.Query("page_size"), 20)
	page, size = max(page, 1), min(max(size, 1), 100)
	items, total, err := h.service.List(c.Request.Context(), c.Query("start_date"), c.Query("end_date"), page, size)
	result := make([]LogResponse, 0, len(items))
	for _, item := range items {
		result = append(result, toLogResponse(item))
	}
	writeResult(c, gin.H{"items": result, "total": total, "page": page, "page_size": size}, err)
}
func (h *LogHandler) deleteMany(c *gin.Context) {
	var body DeleteLogsRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	removed, err := h.service.Delete(c.Request.Context(), body.IDs)
	writeResult(c, gin.H{"removed": removed}, err)
}
func toLogResponse(item repository.Log) LogResponse {
	return LogResponse{ID: item.ID, Time: item.Time, Summary: item.Summary, Detail: item.Detail}
}

type LogResponse struct {
	ID      string         `json:"id"`
	Time    time.Time      `json:"time"`
	Summary string         `json:"summary"`
	Detail  map[string]any `json:"detail"`
}
type DeleteLogsRequest struct {
	IDs []string `json:"ids"`
}
