package service

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/md5"
	"encoding/hex"
	"errors"
	"io"
	"image"
	"image/png"
	"mime"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/basketikun/chatgpt2api/internal/config"
	"github.com/basketikun/chatgpt2api/internal/repository"
	"github.com/disintegration/imaging"
	"github.com/studio-b12/gowebdav"
)

type ImageService struct {
	repo   *repository.Repository
	config *config.Config
	root   string
	mu     sync.Mutex
}

type StoredImage struct {
	Rel     string
	URL     string
	Storage string
	Size    int64
}

func NewImageService(repo *repository.Repository, config *config.Config) *ImageService {
	return &ImageService{repo: repo, config: config, root: filepath.Join("data", "images")}
}

func (s *ImageService) Save(ctx context.Context, data []byte, baseURL string) (StoredImage, error) {
	digest := md5.Sum(data)
	now := time.Now()
	rel := filepath.ToSlash(filepath.Join(now.Format("2006"), now.Format("01"), now.Format("02"), strconvTime(now)+"_"+hex.EncodeToString(digest[:])+".png"))
	settings := s.config.Image.Storage
	local, webdav := settings.Mode != "webdav", settings.Enabled && (settings.Mode == "webdav" || settings.Mode == "both")
	remote := ""
	if local {
		path, err := s.path(rel)
		if err != nil {
			return StoredImage{}, err
		}
		if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
			return StoredImage{}, err
		}
		if err := os.WriteFile(path, data, 0644); err != nil {
			return StoredImage{}, err
		}
	}
	if webdav {
		client := s.webdav()
		if err := client.MkdirAll(filepath.ToSlash(filepath.Dir(filepath.Join(settings.WebDAVRootPath, rel))), 0755); err != nil {
			return StoredImage{}, err
		}
		remote = strings.TrimSuffix(settings.WebDAVURL, "/") + "/" + filepath.ToSlash(filepath.Join(settings.WebDAVRootPath, rel))
		if err := client.Write(filepath.ToSlash(filepath.Join(settings.WebDAVRootPath, rel)), data, 0644); err != nil {
			return StoredImage{}, err
		}
	}
	width, height := imageSize(data)
	storage := "local"
	if webdav {
		storage = "webdav"
	}
	if local && webdav {
		storage = "both"
	}
	item := repository.File{Path: rel, Kind: "image", Name: filepath.Base(rel), Date: now.Format("2006-01-02"), Size: int64(len(data)), ContentType: "image/png", Storage: storage, Local: local, WebDAV: webdav, RemoteURL: remote, Width: width, Height: height, CreatedAt: now.Format("2006-01-02 15:04:05")}
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.repo.SaveFile(ctx, item); err != nil {
		return StoredImage{}, err
	}
	public := settings.PublicBaseURL
	if public == "" {
		public = baseURL + "/images"
	}
	return StoredImage{Rel: rel, URL: strings.TrimSuffix(public, "/") + "/" + rel, Storage: storage, Size: int64(len(data))}, nil
}

func (s *ImageService) Bytes(ctx context.Context, rel string) ([]byte, error) {
	path, err := s.path(rel)
	if err != nil {
		return nil, err
	}
	if data, err := os.ReadFile(path); err == nil {
		return data, nil
	}
	item, err := s.repo.File(ctx, rel)
	if err != nil || !item.WebDAV {
		return nil, repository.ErrNotFound
	}
	return s.webdav().Read(filepath.ToSlash(filepath.Join(s.config.Image.Storage.WebDAVRootPath, rel)))
}
func (s *ImageService) Thumbnail(ctx context.Context, rel string) (string, error) {
	target, err := s.thumbnailPath(rel)
	if err != nil {
		return "", err
	}
	sourcePath, localErr := s.LocalPath(rel)
	if targetInfo, err := os.Stat(target); err == nil {
		if localErr != nil {
			return target, nil
		}
		if sourceInfo, err := os.Stat(sourcePath); err == nil && !targetInfo.ModTime().Before(sourceInfo.ModTime()) {
			return target, nil
		}
	}
	var source image.Image
	if localErr == nil {
		source, err = imaging.Open(sourcePath)
	} else {
		var data []byte
		data, err = s.Bytes(ctx, rel)
		if err == nil {
			source, err = imaging.Decode(bytes.NewReader(data))
		}
	}
	if err != nil {
		return "", err
	}
	if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
		return "", err
	}
	if err := imaging.Save(imaging.Thumbnail(source, 320, 320, imaging.Lanczos), target); err != nil {
		return "", err
	}
	return target, nil
}
func (s *ImageService) LocalPath(rel string) (string, error) {
	path, err := s.path(rel)
	if err != nil {
		return "", err
	}
	if info, err := os.Stat(path); err != nil || info.IsDir() {
		return "", repository.ErrNotFound
	}
	return path, nil
}

func (s *ImageService) List(ctx context.Context, baseURL string, query string, startDate string, endDate string) ([]map[string]any, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	items, err := s.repo.Files(ctx, "image")
	if err != nil {
		return nil, err
	}
	indexed := map[string]repository.File{}
	for _, item := range items {
		if isImagePath(item.Path) {
			indexed[item.Path] = item
		}
	}
	local, err := s.localImages()
	if err != nil {
		return nil, err
	}
	for _, file := range local {
		if _, ok := indexed[file.rel]; ok {
			continue
		}
		item := localFile(file.rel, file.path, file.info)
		if err := s.repo.SaveFile(ctx, item); err != nil {
			return nil, err
		}
		indexed[file.rel] = item
	}
	items = items[:0]
	for rel, item := range indexed {
		_, err := os.Stat(filepath.Join(s.root, filepath.FromSlash(rel)))
		hasLocal := err == nil
		if !hasLocal && !item.WebDAV {
			if err := s.repo.DeleteFile(ctx, rel); err != nil {
				return nil, err
			}
			delete(indexed, rel)
			continue
		}
		storage := "local"
		if item.WebDAV {
			storage = "webdav"
		}
		if hasLocal && item.WebDAV {
			storage = "both"
		}
		if item.Local != hasLocal || item.Storage != storage {
			item.Local, item.Storage = hasLocal, storage
			if err := s.repo.SaveFile(ctx, item); err != nil {
				return nil, err
			}
		}
		items = append(items, item)
	}
	sort.Slice(items, func(i, j int) bool { return items[i].CreatedAt > items[j].CreatedAt })
	result := []map[string]any{}
	apiBase := s.config.BaseURL
	if apiBase == "" {
		apiBase = baseURL
	}
	public := s.config.Image.Storage.PublicBaseURL
	for _, item := range items {
		if query != "" && !strings.Contains(item.Name, query) || startDate != "" && item.Date < startDate || endDate != "" && item.Date > endDate {
			continue
		}
		imageURL := strings.TrimSuffix(apiBase, "/") + "/images/" + item.Path
		if public != "" {
			imageURL = strings.TrimSuffix(public, "/") + "/" + item.Path
		}
		result = append(result, map[string]any{"rel": item.Path, "path": item.Path, "kind": item.Kind, "name": item.Name, "date": item.Date, "size": item.Size, "content_type": item.ContentType, "storage": item.Storage, "local": item.Local, "webdav": item.WebDAV, "remote_url": item.RemoteURL, "width": item.Width, "height": item.Height, "created_at": item.CreatedAt, "url": imageURL, "thumbnail_url": strings.TrimSuffix(apiBase, "/") + "/image-thumbnails/" + item.Path})
	}
	return result, nil
}

func (s *ImageService) Delete(ctx context.Context, rel string) (bool, error) {
	path, err := s.path(rel)
	if err != nil {
		return false, err
	}
	removed := false
	if os.Remove(path) == nil {
		removed = true
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	item, err := s.repo.File(ctx, rel)
	if err == nil && item.WebDAV {
		if err := s.webdav().Remove(filepath.ToSlash(filepath.Join(s.config.Image.Storage.WebDAVRootPath, rel))); err == nil {
			removed = true
		} else if !removed {
			return false, err
		}
	}
	if err := s.repo.DeleteFile(ctx, rel); err != nil {
		return removed, err
	}
	if thumbnail, err := s.thumbnailPath(rel); err == nil {
		os.Remove(thumbnail)
	}
	return removed, nil
}

func (s *ImageService) DeleteMatching(ctx context.Context, paths []string, query string, startDate string, endDate string, all bool) (int, error) {
	if all {
		items, err := s.List(ctx, "", query, startDate, endDate)
		if err != nil {
			return 0, err
		}
		paths = paths[:0]
		for _, item := range items {
			paths = append(paths, item["path"].(string))
		}
	}
	removed := 0
	for _, path := range paths {
		ok, err := s.Delete(ctx, path)
		if err != nil {
			return removed, err
		}
		if ok {
			removed++
		}
	}
	return removed, nil
}

func (s *ImageService) Zip(ctx context.Context, paths []string, output io.Writer) error {
	writer := zip.NewWriter(output)
	added := 0
	names := map[string]int{}
	for _, path := range paths {
		data, err := s.Bytes(ctx, path)
		if err != nil {
			continue
		}
		name := filepath.Base(path)
		names[name]++
		if names[name] > 1 {
			ext := filepath.Ext(name)
			name = strings.TrimSuffix(name, ext) + "_" + strconv.Itoa(names[name]) + ext
		}
		entry, _ := writer.Create(name)
		entry.Write(data)
		added++
	}
	if added == 0 {
		return repository.ErrNotFound
	}
	return writer.Close()
}

func (s *ImageService) Sync(ctx context.Context) (map[string]int, error) {
	if !s.config.Image.Storage.Enabled || s.config.Image.Storage.Mode == "local" {
		return nil, errors.New("WebDAV 图片存储未启用")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	items, err := s.repo.Files(ctx, "image")
	if err != nil {
		return nil, err
	}
	indexed := map[string]repository.File{}
	for _, item := range items {
		if isImagePath(item.Path) {
			indexed[item.Path] = item
		}
	}
	local, err := s.localImages()
	if err != nil {
		return nil, err
	}
	uploaded, skipped, failed := 0, 0, 0
	client := s.webdav()
	for _, file := range local {
		item, exists := indexed[file.rel]
		if item.WebDAV {
			skipped++
			continue
		}
		data, err := os.ReadFile(file.path)
		if err != nil {
			failed++
			continue
		}
		current := item
		item = localFile(file.rel, file.path, file.info)
		if exists {
			item.ID, item.ContentType, item.CreatedAt = current.ID, current.ContentType, current.CreatedAt
		}
		remote := filepath.ToSlash(filepath.Join(s.config.Image.Storage.WebDAVRootPath, file.rel))
		if err := client.MkdirAll(filepath.Dir(remote), 0755); err != nil {
			failed++
			continue
		}
		if err := client.Write(remote, data, 0644); err != nil {
			failed++
			continue
		}
		item.Local, item.WebDAV, item.Storage, item.RemoteURL = true, true, "both", strings.TrimSuffix(s.config.Image.Storage.WebDAVURL, "/")+"/"+remote
		if err := s.repo.SaveFile(ctx, item); err != nil {
			failed++
			continue
		}
		uploaded++
	}
	return map[string]int{"uploaded": uploaded, "skipped": skipped, "failed": failed}, nil
}

func (s *ImageService) TestWebDAV() map[string]any {
	if s.config.Image.Storage.WebDAVURL == "" {
		return map[string]any{"ok": false, "status": 0, "error": "WebDAV URL is required"}
	}
	client := s.webdav()
	path := filepath.ToSlash(filepath.Join(s.config.Image.Storage.WebDAVRootPath, ".chatgpt2api_webdav_test.txt"))
	err := client.Write(path, []byte("chatgpt2api webdav test\n"), 0644)
	if err == nil {
		err = client.Remove(path)
	}
	if err != nil {
		return map[string]any{"ok": false, "status": 0, "error": err.Error()}
	}
	return map[string]any{"ok": true, "status": 200, "error": nil}
}

func (s *ImageService) Stats() (map[string]any, error) {
	os.MkdirAll(s.root, 0755)
	total, free, err := diskUsage(s.root)
	if err != nil {
		return nil, err
	}
	var count, size int64
	filepath.Walk(s.root, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && !strings.HasSuffix(info.Name(), "_thumbnail.png") {
			count++
			size += info.Size()
		}
		return nil
	})
	return map[string]any{"disk_total_mb": total / 1024 / 1024, "disk_used_mb": (total - free) / 1024 / 1024, "disk_free_mb": free / 1024 / 1024, "image_count": count, "image_size_mb": size / 1024 / 1024, "image_size_bytes": size}, nil
}

func (s *ImageService) Compress() (map[string]int64, error) {
	paths := []string{}
	filepath.Walk(s.root, func(path string, info os.FileInfo, err error) error {
		if err == nil && !info.IsDir() && filepath.Ext(path) == ".png" && !strings.HasSuffix(info.Name(), "_thumbnail.png") {
			paths = append(paths, path)
		}
		return nil
	})
	sort.Strings(paths)
	var saved, count int64
	for _, path := range paths {
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		source, err := png.Decode(bytes.NewReader(data))
		if err != nil {
			continue
		}
		buffer := bytes.NewBuffer(nil)
		encoder := png.Encoder{CompressionLevel: png.BestCompression}
		if encoder.Encode(buffer, source) == nil && buffer.Len() < len(data) {
			os.WriteFile(path, buffer.Bytes(), 0644)
			saved += int64(len(data) - buffer.Len())
			count++
		}
	}
	return map[string]int64{"compressed": count, "saved_bytes": saved, "saved_mb": saved / 1024 / 1024}, nil
}

func (s *ImageService) Cleanup(ctx context.Context, targetMB int64, dryRun bool) (map[string]any, error) {
	stats, err := s.Stats()
	if err != nil {
		return nil, err
	}
	free := int64(stats["disk_free_mb"].(uint64))
	items, err := s.localImages()
	if err != nil {
		return nil, err
	}
	pngs := items[:0]
	for _, item := range items {
		if filepath.Ext(item.path) == ".png" {
			pngs = append(pngs, item)
		}
	}
	items = pngs
	sort.Slice(items, func(i, j int) bool { return items[i].info.ModTime().Before(items[j].info.ModTime()) })
	removed, freed := 0, int64(0)
	for _, item := range items {
		if free+freed/1024/1024 >= targetMB {
			break
		}
		if !dryRun {
			if thumbnail, err := s.thumbnailPath(item.rel); err == nil {
				os.Remove(thumbnail)
			}
			if err := os.Remove(item.path); err != nil {
				continue
			}
		}
		freed += item.info.Size()
		removed++
	}
	if !dryRun {
		s.cleanupEmptyDirs()
	}
	return map[string]any{"removed": removed, "freed_mb": freed / 1024 / 1024, "target_free_mb": targetMB, "current_free_mb": free + freed/1024/1024, "done": free+freed/1024/1024 >= targetMB, "dry_run": dryRun}, nil
}
func (s *ImageService) CleanupExpired(ctx context.Context) error {
	if err := os.MkdirAll(s.root, 0755); err != nil {
		return err
	}
	cutoffTime := time.Now().Add(-time.Duration(s.config.Image.RetentionDays) * 24 * time.Hour)
	err := filepath.Walk(s.root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if err == nil && !info.IsDir() && info.ModTime().Before(cutoffTime) {
			return os.Remove(path)
		}
		return nil
	})
	if err == nil {
		filepath.Walk(s.root, func(path string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() || !strings.HasSuffix(info.Name(), "_thumbnail.png") {
				return nil
			}
			stem := strings.TrimSuffix(path, "_thumbnail.png")
			for _, ext := range []string{".png", ".jpg", ".jpeg", ".webp"} {
				if _, err := os.Stat(stem + ext); err == nil {
					return nil
				}
			}
			return os.Remove(path)
		})
		s.cleanupEmptyDirs()
	}
	return err
}

func (s *ImageService) path(rel string) (string, error) {
	if rel == "" || filepath.IsAbs(rel) {
		return "", repository.ErrNotFound
	}
	root, _ := filepath.Abs(s.root)
	path, _ := filepath.Abs(filepath.Join(root, filepath.FromSlash(rel)))
	if path != root && !strings.HasPrefix(path, root+string(os.PathSeparator)) {
		return "", repository.ErrNotFound
	}
	return path, nil
}
func (s *ImageService) webdav() *gowebdav.Client {
	settings := s.config.Image.Storage
	return gowebdav.NewClient(settings.WebDAVURL, settings.WebDAVUsername, settings.WebDAVPassword)
}

type localImage struct {
	path string
	rel  string
	info os.FileInfo
}

func (s *ImageService) localImages() ([]localImage, error) {
	if err := os.MkdirAll(s.root, 0755); err != nil {
		return nil, err
	}
	items := []localImage{}
	err := filepath.Walk(s.root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if !info.IsDir() {
			rel, _ := filepath.Rel(s.root, path)
			if isImagePath(rel) {
				items = append(items, localImage{path: path, rel: filepath.ToSlash(rel), info: info})
			}
		}
		return nil
	})
	return items, err
}
func (s *ImageService) thumbnailPath(rel string) (string, error) {
	path, err := s.path(rel)
	if err != nil {
		return "", err
	}
	return strings.TrimSuffix(path, filepath.Ext(path)) + "_thumbnail.png", nil
}
func (s *ImageService) cleanupEmptyDirs() {
	dirs := []string{}
	filepath.Walk(s.root, func(path string, info os.FileInfo, err error) error {
		if err == nil && info.IsDir() && path != s.root {
			dirs = append(dirs, path)
		}
		return nil
	})
	sort.Slice(dirs, func(i, j int) bool { return len(dirs[i]) > len(dirs[j]) })
	for _, dir := range dirs {
		os.Remove(dir)
	}
}
func localFile(rel string, path string, info os.FileInfo) repository.File {
	parts := strings.Split(filepath.ToSlash(rel), "/")
	date := info.ModTime().Format("2006-01-02")
	if len(parts) >= 4 {
		date = strings.Join(parts[:3], "-")
	}
	var width, height *int
	if file, err := os.Open(path); err == nil {
		if value, _, err := image.DecodeConfig(file); err == nil {
			width, height = &value.Width, &value.Height
		}
		file.Close()
	}
	return repository.File{Path: filepath.ToSlash(rel), Kind: "image", Name: filepath.Base(rel), Date: date, Size: info.Size(), Storage: "local", Local: true, Width: width, Height: height, CreatedAt: info.ModTime().Format("2006-01-02 15:04:05")}
}
func isImagePath(path string) bool {
	name := filepath.Base(path)
	if strings.HasSuffix(name, "_thumbnail.png") {
		return false
	}
	switch strings.ToLower(filepath.Ext(name)) {
	case ".png", ".jpg", ".jpeg", ".webp":
		return true
	default:
		return false
	}
}
func imageSize(data []byte) (*int, *int) {
	value, _, err := image.DecodeConfig(bytes.NewReader(data))
	if err != nil {
		return nil, nil
	}
	return &value.Width, &value.Height
}
func strconvTime(value time.Time) string { return strconv.FormatInt(value.Unix(), 10) }
func ContentType(path string) string {
	value := mime.TypeByExtension(filepath.Ext(path))
	if value == "" {
		return "application/octet-stream"
	}
	return value
}
