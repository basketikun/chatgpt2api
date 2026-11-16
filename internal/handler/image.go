package handler

import (
	"errors"
	"net/http"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/basketikun/chatgpt2api/internal/repository"
	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
)

type ImageHandler struct {
	service *service.ImageService
	slots   chan struct{}
}

func NewImageHandler(service *service.ImageService) *ImageHandler {
	return &ImageHandler{service: service, slots: make(chan struct{}, 4)}
}
func (h *ImageHandler) RegisterPublic(router *gin.Engine) {
	router.GET("/images/*path", h.image)
	router.GET("/image-thumbnails/*path", h.thumbnail)
}
func (h *ImageHandler) RegisterRoutes(router *gin.RouterGroup) {
	router.GET("/images", h.list)
	router.POST("/images/delete", h.delete)
	router.POST("/images/download", h.zip)
	router.GET("/images/download/*path", h.download)
	router.POST("/image-storage/test", h.test)
	router.POST("/image-storage/sync", h.sync)
	router.GET("/images/storage", h.storage)
	router.POST("/images/storage/compress", h.compress)
	router.POST("/images/storage/cleanup-to-target", h.cleanup)
}

func (h *ImageHandler) image(c *gin.Context) {
	rel := strings.TrimPrefix(c.Param("path"), "/")
	if path, err := h.service.LocalPath(rel); err == nil {
		c.Header("Cache-Control", "public, max-age=31536000, immutable")
		c.File(path)
		return
	}
	select {
	case h.slots <- struct{}{}:
		defer func() { <-h.slots }()
	case <-c.Request.Context().Done():
		return
	}
	data, err := h.service.Bytes(c.Request.Context(), rel)
	if err != nil {
		writeError(c, http.StatusNotFound, errors.New("image not found"))
		return
	}
	c.Data(http.StatusOK, service.ContentType(rel), data)
}
func (h *ImageHandler) thumbnail(c *gin.Context) {
	rel := strings.TrimPrefix(c.Param("path"), "/")
	select {
	case h.slots <- struct{}{}:
		defer func() { <-h.slots }()
	case <-c.Request.Context().Done():
		return
	}
	path, err := h.service.Thumbnail(c.Request.Context(), rel)
	if err != nil {
		writeError(c, http.StatusNotFound, errors.New("image not found"))
		return
	}
	c.Header("Cache-Control", "public, max-age=31536000, immutable")
	c.File(path)
}
func (h *ImageHandler) list(c *gin.Context) {
	items, err := h.service.List(c.Request.Context(), requestBaseURL(c), c.Query("query"), c.Query("start_date"), c.Query("end_date"))
	groups := []gin.H{}
	grouped := map[string][]map[string]any{}
	order := []string{}
	for _, item := range items {
		date := item["date"].(string)
		if grouped[date] == nil {
			order = append(order, date)
		}
		grouped[date] = append(grouped[date], item)
	}
	for _, date := range order {
		groups = append(groups, gin.H{"date": date, "items": grouped[date]})
	}
	writeResult(c, gin.H{"items": items, "groups": groups}, err)
}
func (h *ImageHandler) delete(c *gin.Context) {
	var body DeleteImagesRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	removed, err := h.service.DeleteMatching(c.Request.Context(), body.Paths, body.Query, body.StartDate, body.EndDate, body.All)
	writeResult(c, gin.H{"removed": removed}, err)
}
func (h *ImageHandler) zip(c *gin.Context) {
	var body DownloadImagesRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	c.Header("Content-Type", "application/zip")
	c.Header("Content-Disposition", `attachment; filename="images.zip"`)
	err := h.service.Zip(c.Request.Context(), body.Paths, c.Writer)
	if errors.Is(err, repository.ErrNotFound) {
		c.Writer.Header().Del("Content-Disposition")
		writeError(c, http.StatusNotFound, errors.New("no images found"))
		return
	}
	if err != nil {
		c.Abort()
	}
}
func (h *ImageHandler) download(c *gin.Context) {
	rel := strings.TrimPrefix(c.Param("path"), "/")
	data, err := h.service.Bytes(c.Request.Context(), rel)
	if err != nil {
		writeError(c, http.StatusNotFound, errors.New("image not found"))
		return
	}
	c.Header("Content-Disposition", `attachment; filename="`+filepath.Base(rel)+`"`)
	c.Data(http.StatusOK, service.ContentType(rel), data)
}
func (h *ImageHandler) test(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"result": h.service.TestWebDAV()})
}
func (h *ImageHandler) sync(c *gin.Context) {
	result, err := h.service.Sync(c.Request.Context())
	if err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"result": result})
}
func (h *ImageHandler) storage(c *gin.Context) {
	result, err := h.service.Stats()
	writeResult(c, result, err)
}
func (h *ImageHandler) compress(c *gin.Context) {
	result, err := h.service.Compress()
	writeResult(c, result, err)
}
func (h *ImageHandler) cleanup(c *gin.Context) {
	target, _ := strconv.ParseInt(c.DefaultQuery("target_free_mb", "500"), 10, 64)
	dry, _ := strconv.ParseBool(c.DefaultQuery("dry_run", "false"))
	result, err := h.service.Cleanup(c.Request.Context(), target, dry)
	writeResult(c, result, err)
}
func requestBaseURL(c *gin.Context) string {
	scheme := "http"
	if c.Request.TLS != nil {
		scheme = "https"
	}
	if value := c.GetHeader("X-Forwarded-Proto"); value != "" {
		scheme = value
	}
	return scheme + "://" + c.Request.Host
}

type DeleteImagesRequest struct {
	Paths     []string `json:"paths"`
	Query     string   `json:"query"`
	StartDate string   `json:"start_date"`
	EndDate   string   `json:"end_date"`
	All       bool     `json:"all_matching"`
}
type DownloadImagesRequest struct {
	Paths []string `json:"paths" binding:"required"`
}
