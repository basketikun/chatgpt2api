package upstream

import (
	"bytes"
	"crypto/rand"
	"crypto/sha3"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"math/big"
	"regexp"
	"time"

	"github.com/google/uuid"
	"golang.org/x/net/html"
)

type ScriptSrcParser struct {
	ScriptSources []string
	DataBuild     string
	BuildNumber   string
}

type POW struct{}

var processStarted = time.Now()

var navigatorKeys = []string{
	"registerProtocolHandler−function registerProtocolHandler() { [native code] }", "storage−[object StorageManager]", "locks−[object LockManager]", "appCodeName−Mozilla", "permissions−[object Permissions]", "share−function share() { [native code] }", "webdriver−false", "managed−[object NavigatorManagedData]", "canShare−function canShare() { [native code] }", "vendor−Google Inc.", "mediaDevices−[object MediaDevices]", "vibrate−function vibrate() { [native code] }", "storageBuckets−[object StorageBucketManager]", "mediaCapabilities−[object MediaCapabilities]", "cookieEnabled−true", "virtualKeyboard−[object VirtualKeyboard]", "product−Gecko", "presentation−[object Presentation]", "onLine−true", "mimeTypes−[object MimeTypeArray]", "credentials−[object CredentialsContainer]", "serviceWorker−[object ServiceWorkerContainer]", "keyboard−[object Keyboard]", "gpu−[object GPU]", "doNotTrack", "serial−[object Serial]", "pdfViewerEnabled−true", "language−zh-CN", "geolocation−[object Geolocation]", "userAgentData−[object NavigatorUAData]", "getUserMedia−function getUserMedia() { [native code] }", "sendBeacon−function sendBeacon() { [native code] }", "hardwareConcurrency−32", "windowControlsOverlay−[object WindowControlsOverlay]",
}

var windowKeys = []string{
	"0", "window", "self", "document", "name", "location", "customElements", "history", "navigation", "innerWidth", "innerHeight", "scrollX", "scrollY", "visualViewport", "screenX", "screenY", "outerWidth", "outerHeight", "devicePixelRatio", "screen", "chrome", "navigator", "onresize", "performance", "crypto", "indexedDB", "sessionStorage", "localStorage", "scheduler", "alert", "atob", "btoa", "fetch", "matchMedia", "postMessage", "queueMicrotask", "requestAnimationFrame", "setInterval", "setTimeout", "caches", "__NEXT_DATA__", "__BUILD_MANIFEST", "__NEXT_PRELOADREADY",
}

func (p POW) BuildPToken(userAgent string, scriptSources []string, dataBuild string) string {
	config := p.BuildConfig(userAgent, scriptSources, dataBuild)
	data, _ := json.Marshal(config)
	return "gAAAAAC" + base64.StdEncoding.EncodeToString(data)
}

func (p POW) BuildProofToken(seed string, difficulty string, userAgent string, scriptSources []string, dataBuild string) (string, error) {
	config := p.BuildConfig(userAgent, scriptSources, dataBuild)
	target, err := hex.DecodeString(difficulty)
	if err != nil {
		return "", err
	}
	seedBytes := []byte(seed)
	for nonce := range 500000 {
		config[3], config[9] = nonce, nonce>>1
		data, _ := json.Marshal(config)
		encoded := base64.StdEncoding.EncodeToString(data)
		digest := sha3.Sum512(append(seedBytes, []byte(encoded)...))
		if bytes.Compare(digest[:len(target)], target) <= 0 {
			return "gAAAAAB" + encoded, nil
		}
	}
	return "", errors.New("failed to solve proof token")
}

func (POW) BuildConfig(userAgent string, scriptSources []string, dataBuild string) []any {
	cores := []int{8, 16, 24, 32}
	screens := []int{3000, 2340, 4000, 6000}
	document := []string{"__reactContainer$fzelfjyxej8", "_reactListening5dehydibo78", "location"}
	scriptSource := "https://chatgpt.com/backend-api/sentinel/sdk.js"
	if len(scriptSources) > 0 {
		scriptSource = scriptSources[randomIndex(len(scriptSources))]
	}
	elapsed := float64(time.Since(processStarted).Nanoseconds()) / 1e6
	return []any{screens[randomIndex(len(screens))], time.Now().In(time.FixedZone("EST", -5*3600)).Format("Mon Jan 02 2006 15:04:05") + " GMT-0500 (Eastern Standard Time)", 4294705152, 1, userAgent, scriptSource, dataBuild, "en-US", "en-US,es-US,en,es", randomFloat(), navigatorKeys[randomIndex(len(navigatorKeys))], document[randomIndex(len(document))], windowKeys[randomIndex(len(windowKeys))], elapsed, uuid.NewString(), "", cores[randomIndex(len(cores))], float64(time.Now().UnixMilli()) - elapsed, 0, 0, 0, 0, 0, 0, 0}
}

func (p *ScriptSrcParser) Parse(reader io.Reader) error {
	tokenizer := html.NewTokenizer(reader)
	buildPattern := regexp.MustCompile(`c/[^/]*/_`)
	for {
		switch tokenizer.Next() {
		case html.ErrorToken:
			if err := tokenizer.Err(); err != io.EOF {
				return err
			}
			return nil
		case html.StartTagToken, html.SelfClosingTagToken:
			token := tokenizer.Token()
			attrs := map[string]string{}
			for _, attr := range token.Attr {
				attrs[attr.Key] = attr.Val
			}
			if token.Data == "html" {
				p.DataBuild, p.BuildNumber = attrs["data-build"], attrs["data-seq"]
				if p.DataBuild == "" {
					p.DataBuild = attrs["data-client-build-revision"]
				}
			}
			if token.Data == "script" && attrs["src"] != "" {
				p.ScriptSources = append(p.ScriptSources, attrs["src"])
				if p.DataBuild == "" {
					p.DataBuild = buildPattern.FindString(attrs["src"])
				}
			}
		}
	}
}
func randomIndex(limit int) int {
	value, _ := rand.Int(rand.Reader, big.NewInt(int64(limit)))
	return int(value.Int64())
}
func randomFloat() float64 {
	value, _ := rand.Int(rand.Reader, big.NewInt(1<<53))
	return float64(value.Int64()) / float64(1<<53)
}
