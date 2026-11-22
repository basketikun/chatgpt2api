package main

import (
	"context"
	"errors"
	"log"
	"net"
	"net/http"
	"os/signal"
	"syscall"
	"time"

	"github.com/basketikun/chatgpt2api/internal/config"
	"github.com/basketikun/chatgpt2api/internal/handler"
	"github.com/basketikun/chatgpt2api/internal/repository"
	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	cfg, err := config.Load("config.yaml")
	if err != nil {
		log.Fatal(err)
	}
	repo, err := repository.Open(cfg.DatabaseURL)
	if err != nil {
		log.Fatal(err)
	}
	defer repo.Close()
	proxyService := service.NewProxyService(cfg)
	accountService := service.NewAccountService(repo, proxyService)
	imageService := service.NewImageService(repo, cfg)
	logService := service.NewLogService(repo)
	conversationService := service.NewConversationService(repo)
	catalogService := service.NewCatalogService(accountService, proxyService, cfg)
	aiService := service.NewAIService(accountService, catalogService, imageService, logService, proxyService, cfg)
	audioService := service.NewAudioService(accountService, logService, proxyService, cfg)
	authService := service.NewAuthService(repo, cfg.APIKey)
	taskService := service.NewTaskService(repo, aiService, cfg)
	authHandler := handler.NewAuthHandler(authService, cfg.Version)
	systemHandler := handler.NewSystemHandler(cfg, proxyService)
	engine := gin.New()
	engine.Use(gin.Recovery(), handler.CORS, handler.LimitBody(cfg))
	authHandler.RegisterLogin(engine)
	systemHandler.RegisterVersion(engine)
	imageHandler := handler.NewImageHandler(imageService)
	imageHandler.RegisterPublic(engine)
	taskHandler := handler.NewTaskHandler(taskService)
	identity := handler.Identity(authService)
	api := engine.Group("/api", identity)
	handler.NewConversationHandler(conversationService).RegisterRoutes(api)
	taskHandler.RegisterRoutes(api)
	admin := engine.Group("/api", identity, handler.Admin)
	handler.NewAccountHandler(accountService).RegisterRoutes(admin)
	authHandler.RegisterRoutes(admin)
	systemHandler.RegisterRoutes(admin)
	handler.NewOAuthHandler(service.NewOAuthService(proxyService), accountService).RegisterRoutes(admin)
	handler.NewSourceHandler(service.NewSourceService(repo, accountService, proxyService)).RegisterRoutes(admin)
	imageHandler.RegisterRoutes(admin)
	handler.NewLogHandler(logService).RegisterRoutes(admin)
	handler.NewOverviewHandler(service.NewOverviewService(repo)).RegisterRoutes(admin)
	v1 := engine.Group("/v1", identity)
	handler.NewCatalogHandler(catalogService, cfg).RegisterRoutes(v1)
	handler.NewAIHandler(aiService, logService).RegisterRoutes(v1)
	handler.NewAudioHandler(audioService, logService).RegisterRoutes(v1)
	engine.NoRoute(handler.Static("web"))
	repo.FailRunningTasks(context.Background(), time.Now().UTC())
	repo.ResetAccountImageInflight(context.Background())

	scheduler := service.NewScheduler(accountService, imageService, taskService, logService, cfg)
	scheduler.Run(ctx)
	server := &http.Server{Addr: net.JoinHostPort(cfg.Bind, cfg.Port), Handler: engine, ReadHeaderTimeout: 10 * time.Second}
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		server.Shutdown(shutdown)
	}()
	if err = server.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}
