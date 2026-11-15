package handler

import (
	"errors"
	"net/http"
	"strconv"

	"github.com/basketikun/chatgpt2api/internal/repository"
	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
)

type SourceHandler struct{ service *service.SourceService }

func NewSourceHandler(service *service.SourceService) *SourceHandler {
	return &SourceHandler{service: service}
}

func (h *SourceHandler) RegisterRoutes(router *gin.RouterGroup) {
	router.GET("/cpa/pools", h.cpas)
	router.POST("/cpa/pools", h.createCPA)
	router.POST("/cpa/pools/:id", h.updateCPA)
	router.DELETE("/cpa/pools/:id", h.deleteCPA)
	router.GET("/cpa/pools/:id/files", h.cpaFiles)
	router.POST("/cpa/pools/:id/import", h.importCPA)
	router.GET("/cpa/pools/:id/import", h.cpaImport)
	router.GET("/sub2api/servers", h.servers)
	router.POST("/sub2api/servers", h.createServer)
	router.POST("/sub2api/servers/:id", h.updateServer)
	router.DELETE("/sub2api/servers/:id", h.deleteServer)
	router.GET("/sub2api/servers/:id/groups", h.groups)
	router.GET("/sub2api/servers/:id/accounts", h.remoteAccounts)
	router.POST("/sub2api/servers/:id/import", h.importServer)
	router.GET("/sub2api/servers/:id/import", h.serverImport)
}

func (h *SourceHandler) cpas(c *gin.Context) {
	items, err := h.service.CPAs(c.Request.Context())
	result := make([]gin.H, 0, len(items))
	for _, item := range items {
		result = append(result, cpaResponse(item))
	}
	writeResult(c, gin.H{"pools": result}, err)
}
func (h *SourceHandler) createCPA(c *gin.Context) {
	var body CreateCPARequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, errors.New("请填写服务地址和密钥"))
		return
	}
	item, err := h.service.SaveCPA(c.Request.Context(), repository.CPA{Name: body.Name, BaseURL: body.BaseURL, SecretKey: body.SecretKey})
	if err != nil {
		writeResult(c, nil, err)
		return
	}
	items, err := h.service.CPAs(c.Request.Context())
	writeResult(c, gin.H{"pool": cpaResponse(item), "pools": cpaResponses(items)}, err)
}
func (h *SourceHandler) updateCPA(c *gin.Context) {
	item, err := h.service.CPA(c.Request.Context(), c.Param("id"))
	if errors.Is(err, repository.ErrNotFound) {
		writeError(c, http.StatusNotFound, errors.New("pool not found"))
		return
	}
	var body UpdateCPARequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	if body.Name != nil {
		item.Name = *body.Name
	}
	if body.BaseURL != nil {
		item.BaseURL = *body.BaseURL
	}
	if body.SecretKey != nil {
		item.SecretKey = *body.SecretKey
	}
	item, err = h.service.SaveCPA(c.Request.Context(), item)
	if err != nil {
		writeResult(c, nil, err)
		return
	}
	items, err := h.service.CPAs(c.Request.Context())
	writeResult(c, gin.H{"pool": cpaResponse(item), "pools": cpaResponses(items)}, err)
}
func (h *SourceHandler) deleteCPA(c *gin.Context) {
	if _, err := h.service.CPA(c.Request.Context(), c.Param("id")); errors.Is(err, repository.ErrNotFound) {
		writeError(c, http.StatusNotFound, errors.New("pool not found"))
		return
	}
	if err := h.service.DeleteCPA(c.Request.Context(), c.Param("id")); err != nil {
		writeResult(c, nil, err)
		return
	}
	items, err := h.service.CPAs(c.Request.Context())
	writeResult(c, gin.H{"pools": cpaResponses(items)}, err)
}
func (h *SourceHandler) cpaFiles(c *gin.Context) {
	item, err := h.service.CPA(c.Request.Context(), c.Param("id"))
	if err != nil {
		writeError(c, http.StatusNotFound, errors.New("pool not found"))
		return
	}
	files, err := h.service.CPAFiles(c.Request.Context(), item)
	writeResult(c, gin.H{"pool_id": item.ID, "files": files}, err)
}
func (h *SourceHandler) importCPA(c *gin.Context) {
	item, err := h.service.CPA(c.Request.Context(), c.Param("id"))
	if err != nil {
		writeError(c, http.StatusNotFound, errors.New("pool not found"))
		return
	}
	var body ImportCPARequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	job, err := h.service.ImportCPA(c.Request.Context(), item, body.Names)
	writeResult(c, gin.H{"import_job": job}, err)
}
func (h *SourceHandler) cpaImport(c *gin.Context) {
	item, err := h.service.CPA(c.Request.Context(), c.Param("id"))
	var job any
	if item.ImportJob.ID != "" {
		job = item.ImportJob
	}
	writeResult(c, gin.H{"import_job": job}, err)
}

func (h *SourceHandler) servers(c *gin.Context) {
	items, err := h.service.Subs(c.Request.Context())
	result := make([]gin.H, 0, len(items))
	for _, item := range items {
		result = append(result, subResponse(item))
	}
	writeResult(c, gin.H{"servers": result}, err)
}
func (h *SourceHandler) createServer(c *gin.Context) {
	var body CreateSubRequest
	if err := c.ShouldBindJSON(&body); err != nil || body.BaseURL == "" || body.APIKey == "" && (body.Email == "" || body.Password == "") {
		writeError(c, http.StatusBadRequest, errors.New("请填写服务地址以及登录信息或密钥"))
		return
	}
	item, err := h.service.SaveSub(c.Request.Context(), repository.Sub{Name: body.Name, BaseURL: body.BaseURL, Email: body.Email, Password: body.Password, APIKey: body.APIKey, GroupID: body.GroupID})
	if err != nil {
		writeResult(c, nil, err)
		return
	}
	items, err := h.service.Subs(c.Request.Context())
	writeResult(c, gin.H{"server": subResponse(item), "servers": subResponses(items)}, err)
}
func (h *SourceHandler) updateServer(c *gin.Context) {
	item, err := h.service.Sub(c.Request.Context(), c.Param("id"))
	if err != nil {
		writeError(c, http.StatusNotFound, errors.New("server not found"))
		return
	}
	var body UpdateSubRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	if value, ok := body["name"]; ok {
		item.Name = value
	}
	if value, ok := body["base_url"]; ok {
		item.BaseURL = value
	}
	if value, ok := body["email"]; ok {
		item.Email = value
	}
	if value, ok := body["password"]; ok {
		item.Password = value
	}
	if value, ok := body["api_key"]; ok {
		item.APIKey = value
	}
	if value, ok := body["group_id"]; ok {
		item.GroupID = value
	}
	item, err = h.service.SaveSub(c.Request.Context(), item)
	if err != nil {
		writeResult(c, nil, err)
		return
	}
	items, err := h.service.Subs(c.Request.Context())
	writeResult(c, gin.H{"server": subResponse(item), "servers": subResponses(items)}, err)
}
func (h *SourceHandler) deleteServer(c *gin.Context) {
	if _, err := h.service.Sub(c.Request.Context(), c.Param("id")); errors.Is(err, repository.ErrNotFound) {
		writeError(c, http.StatusNotFound, errors.New("server not found"))
		return
	}
	if err := h.service.DeleteSub(c.Request.Context(), c.Param("id")); err != nil {
		writeResult(c, nil, err)
		return
	}
	items, err := h.service.Subs(c.Request.Context())
	writeResult(c, gin.H{"servers": subResponses(items)}, err)
}
func (h *SourceHandler) groups(c *gin.Context) {
	item, err := h.service.Sub(c.Request.Context(), c.Param("id"))
	if err != nil {
		writeError(c, http.StatusNotFound, errors.New("server not found"))
		return
	}
	items, err := h.service.SubGroups(c.Request.Context(), item)
	writeResult(c, gin.H{"server_id": item.ID, "groups": items}, err)
}
func (h *SourceHandler) remoteAccounts(c *gin.Context) {
	item, err := h.service.Sub(c.Request.Context(), c.Param("id"))
	if err != nil {
		writeError(c, http.StatusNotFound, errors.New("server not found"))
		return
	}
	page, _ := strconv.Atoi(c.Query("page"))
	size, _ := strconv.Atoi(c.Query("size"))
	items, total, err := h.service.SubAccounts(c.Request.Context(), item, page, size, c.Query("search"))
	writeResult(c, gin.H{"server_id": item.ID, "accounts": items, "total": total}, err)
}
func (h *SourceHandler) importServer(c *gin.Context) {
	item, err := h.service.Sub(c.Request.Context(), c.Param("id"))
	if err != nil {
		writeError(c, http.StatusNotFound, errors.New("server not found"))
		return
	}
	var body ImportSubRequest
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	job, err := h.service.ImportSub(c.Request.Context(), item, body.IDs, body.All, body.Search)
	writeResult(c, gin.H{"import_job": job}, err)
}
func (h *SourceHandler) serverImport(c *gin.Context) {
	item, err := h.service.Sub(c.Request.Context(), c.Param("id"))
	var job any
	if item.ImportJob.ID != "" {
		job = item.ImportJob
	}
	writeResult(c, gin.H{"import_job": job}, err)
}

func cpaResponse(item repository.CPA) gin.H {
	var job any
	if item.ImportJob.ID != "" {
		job = item.ImportJob
	}
	return gin.H{"id": item.ID, "name": item.Name, "base_url": item.BaseURL, "import_job": job}
}
func subResponse(item repository.Sub) gin.H {
	var job any
	if item.ImportJob.ID != "" {
		job = item.ImportJob
	}
	return gin.H{"id": item.ID, "name": item.Name, "base_url": item.BaseURL, "email": item.Email, "group_id": item.GroupID, "has_api_key": item.APIKey != "", "import_job": job}
}
func cpaResponses(items []repository.CPA) []gin.H {
	result := make([]gin.H, 0, len(items))
	for _, item := range items {
		result = append(result, cpaResponse(item))
	}
	return result
}
func subResponses(items []repository.Sub) []gin.H {
	result := make([]gin.H, 0, len(items))
	for _, item := range items {
		result = append(result, subResponse(item))
	}
	return result
}

type CreateCPARequest struct {
	Name      string `json:"name"`
	BaseURL   string `json:"base_url" binding:"required"`
	SecretKey string `json:"secret_key" binding:"required"`
}
type UpdateCPARequest struct {
	Name      *string `json:"name"`
	BaseURL   *string `json:"base_url"`
	SecretKey *string `json:"secret_key"`
}
type ImportCPARequest struct {
	Names []string `json:"names" binding:"required"`
}
type CreateSubRequest struct {
	Name     string `json:"name"`
	BaseURL  string `json:"base_url"`
	Email    string `json:"email"`
	Password string `json:"password"`
	APIKey   string `json:"api_key"`
	GroupID  string `json:"group_id"`
}
type UpdateSubRequest map[string]string
type ImportSubRequest struct {
	IDs    []string `json:"account_ids"`
	All    bool     `json:"all"`
	Search string   `json:"search"`
}
