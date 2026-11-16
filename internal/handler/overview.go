package handler

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
)

type OverviewHandler struct{ service *service.OverviewService }

func NewOverviewHandler(service *service.OverviewService) *OverviewHandler {
	return &OverviewHandler{service: service}
}

func (h *OverviewHandler) RegisterRoutes(router *gin.RouterGroup) {
	router.GET("/overview/calls", h.calls)
	router.GET("/overview/system", h.system)
}

func (h *OverviewHandler) calls(c *gin.Context) {
	period := c.Query("period")
	if period != "24h" && period != "7d" {
		writeError(c, http.StatusBadRequest, errors.New("请选择近 24 小时或近 7 天"))
		return
	}
	ctx, cancel := context.WithTimeout(c.Request.Context(), 10*time.Second)
	defer cancel()
	result, err := h.service.Calls(ctx, period)
	writeResult(c, result, err)
}

func (h *OverviewHandler) system(c *gin.Context) {
	ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
	defer cancel()
	c.JSON(http.StatusOK, h.service.System(ctx))
}
