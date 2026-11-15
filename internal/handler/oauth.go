package handler

import (
	"errors"
	"net/http"

	"github.com/basketikun/chatgpt2api/internal/repository"
	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
)

type OAuthHandler struct {
	oauth    *service.OAuthService
	accounts *service.AccountService
}

func NewOAuthHandler(oauth *service.OAuthService, accounts *service.AccountService) *OAuthHandler {
	return &OAuthHandler{oauth: oauth, accounts: accounts}
}
func (h *OAuthHandler) RegisterRoutes(router *gin.RouterGroup) {
	router.POST("/accounts/oauth/start", h.start)
	router.POST("/accounts/oauth/finish", h.finish)
	router.POST("/accounts/quota", h.quota)
}
func (h *OAuthHandler) start(c *gin.Context) {
	var body OAuthStartRequest
	c.ShouldBindJSON(&body)
	c.JSON(http.StatusOK, h.oauth.Start(body.Email))
}
func (h *OAuthHandler) finish(c *gin.Context) {
	var body OAuthFinishRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, errors.New("授权信息不完整"))
		return
	}
	tokens, err := h.oauth.Finish(c.Request.Context(), body.SessionID, body.Callback)
	if err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	added, skipped, refreshed, failures, err := h.accounts.Add(c.Request.Context(), []repository.Account{{AccessToken: tokens["access_token"], RefreshToken: tokens["refresh_token"], IDToken: tokens["id_token"]}})
	writeResult(c, gin.H{"added": added, "skipped": skipped, "refreshed": refreshed, "errors": failures}, err)
}
func (h *OAuthHandler) quota(c *gin.Context) {
	refreshed, failures, err := h.accounts.RefreshAll(c.Request.Context())
	writeResult(c, gin.H{"queried": refreshed, "errors": failures}, err)
}

type OAuthStartRequest struct {
	Email string `json:"email_hint"`
}
type OAuthFinishRequest struct {
	SessionID string `json:"session_id" binding:"required"`
	Callback  string `json:"callback" binding:"required"`
}
