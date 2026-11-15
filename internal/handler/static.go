package handler

import (
	"net/http"
	"os"
	"path/filepath"
	"strings"

	"github.com/gin-gonic/gin"
)

func Static(root string) gin.HandlerFunc {
	return func(c *gin.Context) {
		if c.Request.Method != http.MethodGet && c.Request.Method != http.MethodHead {
			c.Status(http.StatusNotFound)
			return
		}
		base, _ := filepath.Abs(root)
		requested, _ := filepath.Abs(filepath.Join(base, filepath.FromSlash(strings.TrimPrefix(c.Request.URL.Path, "/"))))
		if requested != base && !strings.HasPrefix(requested, base+string(os.PathSeparator)) {
			c.Status(http.StatusNotFound)
			return
		}
		// 前端无构建、文件名不带哈希，要求浏览器每次按 Last-Modified 校验，发布后立即生效
		c.Header("Cache-Control", "no-cache")
		if info, err := os.Stat(requested); err == nil && !info.IsDir() {
			c.File(requested)
			return
		}
		if strings.HasPrefix(c.Request.URL.Path, "/assets/") || filepath.Ext(c.Request.URL.Path) != "" {
			c.Status(http.StatusNotFound)
			return
		}
		index := filepath.Join(base, "index.html")
		if _, err := os.Stat(index); err != nil {
			c.Status(http.StatusNotFound)
			return
		}
		c.File(index)
	}
}
