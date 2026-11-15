package handler

import (
	"errors"
	"net/http"

	"github.com/basketikun/chatgpt2api/internal/config"
	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
)

type SystemHandler struct {
	config *config.Config
	proxy  *service.ProxyService
}

func NewSystemHandler(config *config.Config, proxy *service.ProxyService) *SystemHandler {
	return &SystemHandler{config: config, proxy: proxy}
}

func (h *SystemHandler) RegisterVersion(router *gin.Engine) { router.GET("/version", h.version) }

func (h *SystemHandler) RegisterRoutes(router *gin.RouterGroup) {
	router.GET("/settings", h.settings)
	router.POST("/settings", h.updateSettings)
	router.POST("/proxy/test", h.testProxy)
	router.POST("/proxy/clearance/test", h.testClearance)
}

func (h *SystemHandler) testProxy(c *gin.Context) {
	var body ProxyTestRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"result": h.proxy.Test(c.Request.Context(), body.URL)})
}
func (h *SystemHandler) testClearance(c *gin.Context) {
	var body ClearanceTestRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	bundle, err := h.proxy.RefreshClearance(c.Request.Context(), body.TargetURL)
	if err != nil {
		writeResult(c, nil, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"result": gin.H{"ok": true, "cookie_count": len(bundle.Cookies), "expires_at": bundle.ExpiresAt}})
}

func (h *SystemHandler) version(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"version": h.config.Version})
}

func (h *SystemHandler) settings(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{"config": h.config.Public()})
}

func (h *SystemHandler) updateSettings(c *gin.Context) {
	var body map[string]any
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, errors.New("设置内容格式不正确"))
		return
	}
	result, err := h.config.Update(body)
	writeResult(c, gin.H{"config": result}, err)
}

type ProxyTestRequest struct {
	URL string `json:"url"`
}
type ClearanceTestRequest struct {
	TargetURL string `json:"target_url" binding:"required"`
}
