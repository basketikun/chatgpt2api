package handler

import (
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/basketikun/chatgpt2api/internal/repository"
	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
)

type TaskHandler struct{ service *service.TaskService }

func NewTaskHandler(service *service.TaskService) *TaskHandler { return &TaskHandler{service: service} }
func (h *TaskHandler) RegisterRoutes(router *gin.RouterGroup) {
	router.GET("/tasks", h.list)
	router.POST("/tasks/image-generation", h.imageGeneration)
	router.POST("/tasks/image-edit", h.imageEdit)
}

func (h *TaskHandler) list(c *gin.Context) {
	ids := []int64{}
	for _, value := range splitQuery(c.Query("ids")) {
		id, err := strconv.ParseInt(value, 10, 64)
		if err != nil {
			writeError(c, http.StatusBadRequest, errors.New("任务编号格式不正确"))
			return
		}
		ids = append(ids, id)
	}
	items, missing, err := h.service.List(c.Request.Context(), identity(c).ID, ids, splitQuery(c.Query("type")))
	result := make([]gin.H, 0, len(items))
	for _, item := range items {
		result = append(result, taskResponse(item))
	}
	writeResult(c, gin.H{"items": result, "missing_ids": missing}, err)
}
func (h *TaskHandler) imageGeneration(c *gin.Context) {
	var body ImageGenerationRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, errors.New("请填写图片描述"))
		return
	}
	if body.Count == 0 {
		body.Count = 1
	}
	if body.Count < 1 || body.Count > 4 {
		writeError(c, http.StatusBadRequest, errors.New("n must be between 1 and 4"))
		return
	}
	if body.Quality == "" {
		body.Quality = "auto"
	}
	item, err := h.service.SubmitImage(c.Request.Context(), identity(c), service.ImageRequest{Prompt: body.Prompt, Model: body.Model, Count: body.Count, Size: body.Size, Quality: body.Quality, ResponseFormat: "url", BaseURL: requestBaseURL(c)}, body.HistoryID, body.TurnID, "image_generation")
	writeTask(c, item, err)
}
func (h *TaskHandler) imageEdit(c *gin.Context) {
	request, err := parseImageRequest(c)
	if err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	if len(request.Images) == 0 {
		writeError(c, http.StatusBadRequest, errors.New("image file or image_url is required"))
		return
	}
	item, err := h.service.SubmitImage(c.Request.Context(), identity(c), request, request.HistoryID, request.TurnID, "image_edit")
	writeTask(c, item, err)
}
func writeTask(c *gin.Context, item repository.Task, err error) {
	if errors.Is(err, service.ErrTooManyTasks) {
		writeError(c, http.StatusTooManyRequests, err)
		return
	}
	writeResult(c, taskResponse(item), err)
}
func splitQuery(value string) []string {
	if value == "" {
		return nil
	}
	return strings.Split(value, ",")
}
func taskResponse(item repository.Task) gin.H {
	results := make([]gin.H, 0, len(item.Results))
	for _, result := range item.Results {
		results = append(results, gin.H{"position": result.Position, "type": result.Type, "name": result.Name, "url": result.URL, "revised_prompt": result.RevisedPrompt, "content_type": result.ContentType, "size": result.Size})
	}
	return gin.H{"id": item.ID, "title": item.Title, "history_id": item.HistoryID, "turn_id": item.TurnID, "type": item.Type, "status": item.Status, "prompt": item.Prompt, "prompt_deleted": item.PromptDeleted, "results_deleted": item.ResultsDeleted, "model": item.Model, "size": item.Size, "quality": item.Quality, "output_count": item.OutputCount, "error": item.Error, "progress": item.Progress, "duration_ms": item.DurationMS, "input_tokens": item.InputTokens, "output_tokens": item.OutputTokens, "total_tokens": item.TotalTokens, "created_at": item.CreatedAt, "updated_at": item.UpdatedAt, "started_at": item.StartedAt, "ended_at": item.EndedAt, "elapsed_seconds": item.ElapsedSeconds(), "results": results}
}

type ImageGenerationRequest struct {
	Prompt    string `json:"prompt" binding:"required"`
	HistoryID *int64 `json:"history_id"`
	TurnID    *int64 `json:"turn_id"`
	Model     string `json:"model"`
	Count     int    `json:"n"`
	Size      string `json:"size"`
	Quality   string `json:"quality"`
}
