package handler

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"io"
	"mime"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"path"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/basketikun/chatgpt2api/internal/protocol"
	"github.com/basketikun/chatgpt2api/internal/service"
	"github.com/gin-gonic/gin"
)

type AIHandler struct {
	service *service.AIService
	logs    *service.LogService
}

func NewAIHandler(ai *service.AIService, logs *service.LogService) *AIHandler {
	return &AIHandler{service: ai, logs: logs}
}
func (h *AIHandler) RegisterRoutes(router *gin.RouterGroup) {
	router.POST("/images/generations", h.images)
	router.POST("/images/edits", h.images)
	router.POST("/chat/completions", h.chat)
	router.POST("/responses", h.responses)
	router.POST("/messages", h.messages)
}

func (h *AIHandler) chat(c *gin.Context) {
	var body map[string]any
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	model, _ := body["model"].(string)
	if model == "" {
		model = "auto"
		body["model"] = model
	}
	messages := mapMessages(body["messages"])
	if len(messages) == 0 {
		if prompt, ok := body["prompt"].(string); ok {
			messages = []map[string]any{{"role": "user", "content": prompt}}
		}
	}
	if len(messages) == 0 {
		writeError(c, http.StatusBadRequest, errors.New("messages or prompt is required"))
		return
	}
	if err := decodeMessageImages(c.Request.Context(), messages); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	functionTools := hasFunctionTools(body["tools"])
	messages = h.service.PrepareMessages(messages)
	messages = protocol.WithToolPrompt(messages, body["tools"], body["tool_choice"])
	stream, _ := body["stream"].(bool)
	effort := thinkingEffort(body)
	search := protocol.WebSearchRequested(body) && !protocol.HasUnsupportedTools(body["tools"], map[string]bool{"web_search": true, "web_search_preview": true, "web_search_preview_2025_03_11": true})
	if search && protocol.SearchQuery(messages) == "" {
		writeError(c, http.StatusBadRequest, errors.New("messages or prompt is required for web search"))
		return
	}
	includeUsage := false
	if options, ok := body["stream_options"].(map[string]any); ok {
		includeUsage, _ = options["include_usage"].(bool)
	}
	requestData, _ := json.Marshal(messages)
	callLog := h.logs.NewCallLog(identity(c), c.Request.URL.Path, model, "文本生成", string(requestData), time.Now())
	if h.service.IsImageModel(model) || imageModalityRequested(body["modalities"]) {
		id, created := service.NewID("chatcmpl-"), time.Now().Unix()
		request := imageRequestFromMessages(messages, model, body, requestBaseURL(c))
		results, err := h.service.Images(c.Request.Context(), request, callLog)
		if err != nil {
			writeImageError(c, err)
			return
		}
		content := imageMarkdown(results)
		response := map[string]any{
			"id": id, "object": "chat.completion", "created": created, "model": model,
			"choices": []any{map[string]any{"index": 0, "message": map[string]string{"role": "assistant", "content": content}, "finish_reason": "stop"}},
			"usage":   service.ChatImageUsage(request, results),
		}
		if !stream {
			c.JSON(http.StatusOK, response)
			return
		}
		startSSE(c)
		writeSSE(c, map[string]any{"id": id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": []any{map[string]any{"index": 0, "delta": map[string]string{"role": "assistant", "content": content}, "finish_reason": nil}}})
		writeSSE(c, map[string]any{"id": id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": []any{map[string]any{"index": 0, "delta": map[string]any{}, "finish_reason": "stop"}}})
		if includeUsage {
			writeSSE(c, map[string]any{"id": id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": []any{}, "usage": service.ChatImageUsage(request, results)})
		}
		c.Writer.WriteString("data: [DONE]\n\n")
		c.Writer.Flush()
		return
	}
	cacheKey := h.service.ProtocolCacheKey("chat.completions", body, messages, stream)
	if stream {
		var cached []gin.H
		if !search && h.service.CachedProtocol(cacheKey, true, &cached) {
			startSSE(c)
			for _, event := range cached {
				writeSSE(c, event)
			}
			c.Writer.WriteString("data: [DONE]\n\n")
			c.Writer.Flush()
			callLog.Save("命中缓存", "success", nil)
			return
		}
		id, created := service.NewID("chatcmpl-"), time.Now().Unix()
		startSSE(c)
		events := []gin.H{}
		emit := func(event gin.H) {
			events = append(events, event)
			writeSSE(c, event)
		}
		emit(gin.H{"id": id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": []any{map[string]any{"index": 0, "delta": map[string]string{"role": "assistant"}, "finish_reason": nil}}})
		output := strings.Builder{}
		success := true
		if functionTools {
			text, err := h.service.Text(c.Request.Context(), model, messages, effort, search, nil, callLog)
			output.WriteString(text)
			calls := protocol.ParseToolCalls(text)
			if err != nil {
				success = false
				emit(gin.H{"error": gin.H{"message": err.Error(), "type": "upstream_error"}})
			} else {
				delta := gin.H{"content": protocol.VisibleToolText(text)}
				if len(calls) > 0 {
					delta["tool_calls"] = openAIToolCalls(calls)
				}
				emit(gin.H{"id": id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": []any{map[string]any{"index": 0, "delta": delta, "finish_reason": nil}}})
				reason := "stop"
				if len(calls) > 0 {
					reason = "tool_calls"
				}
				emit(gin.H{"id": id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": []any{map[string]any{"index": 0, "delta": map[string]any{}, "finish_reason": reason}}})
			}
		} else {
			_, err := h.service.Text(c.Request.Context(), model, messages, effort, search, func(delta string) error {
				output.WriteString(delta)
				emit(gin.H{"id": id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": []any{map[string]any{"index": 0, "delta": map[string]string{"content": delta}, "finish_reason": nil}}})
				return nil
			}, callLog)
			if err != nil {
				success = false
				emit(gin.H{"error": gin.H{"message": err.Error(), "type": "upstream_error"}})
			} else {
				emit(gin.H{"id": id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": []any{map[string]any{"index": 0, "delta": map[string]any{}, "finish_reason": "stop"}}})
			}
		}
		if includeUsage {
			emit(gin.H{"id": id, "object": "chat.completion.chunk", "created": created, "model": model, "choices": []any{}, "usage": service.CompletionUsage(messages, output.String(), model)})
		}
		if success && !search {
			h.service.StoreProtocol(cacheKey, true, events)
		}
		c.Writer.WriteString("data: [DONE]\n\n")
		c.Writer.Flush()
		return
	}
	var cached gin.H
	if !search && h.service.CachedProtocol(cacheKey, false, &cached) {
		c.JSON(http.StatusOK, cached)
		callLog.Save("命中缓存", "success", nil)
		return
	}
	id, created := service.NewID("chatcmpl-"), time.Now().Unix()
	text, err := h.service.Text(c.Request.Context(), model, messages, effort, search, nil, callLog)
	if err != nil {
		writeError(c, http.StatusBadGateway, err)
		return
	}
	message := gin.H{"role": "assistant", "content": text}
	finish := "stop"
	if functionTools {
		calls := protocol.ParseToolCalls(text)
		if len(calls) > 0 {
			message["content"] = protocol.VisibleToolText(text)
			message["tool_calls"] = openAIToolCalls(calls)
			finish = "tool_calls"
		}
	}
	response := gin.H{
		"id": id, "object": "chat.completion", "created": created, "model": model,
		"choices": []any{map[string]any{"index": 0, "message": message, "finish_reason": finish}},
		"usage":   service.CompletionUsage(messages, text, model),
	}
	if search {
		annotations := protocol.SearchAnnotations(text)
		if len(annotations) > 0 {
			items := make([]gin.H, 0, len(annotations))
			for _, annotation := range annotations {
				items = append(items, gin.H{"type": "url_citation", "url_citation": annotation})
			}
			message["annotations"] = items
		}
	}
	if !search {
		h.service.StoreProtocol(cacheKey, false, response)
	}
	c.JSON(http.StatusOK, response)
}

func (h *AIHandler) responses(c *gin.Context) {
	var body map[string]any
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	model, _ := body["model"].(string)
	if model == "" {
		model = "auto"
		body["model"] = model
	}
	messages := protocol.MessagesFromInput(body["input"], body["instructions"])
	if err := decodeMessageImages(c.Request.Context(), messages); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	functionTools := hasFunctionTools(body["tools"])
	messages = h.service.PrepareMessages(messages)
	messages = protocol.WithToolPrompt(messages, body["tools"], body["tool_choice"])
	stream, _ := body["stream"].(bool)
	search := protocol.ResponseSearchRequested(body) && !protocol.HasUnsupportedTools(body["tools"], map[string]bool{"function": true, "image_generation": true, "web_search": true, "web_search_preview": true, "web_search_preview_2025_03_11": true})
	if search {
		functionTools = false
	}
	if search && protocol.SearchQuery(messages) == "" {
		writeError(c, http.StatusBadRequest, errors.New("input text is required for web_search"))
		return
	}
	requestData, _ := json.Marshal(messages)
	callLog := h.logs.NewCallLog(identity(c), c.Request.URL.Path, model, "Responses", string(requestData), time.Now())
	if imageGenerationRequested(body["tools"]) {
		id, created := service.NewID("resp_"), time.Now().Unix()
		request := imageRequestFromMessages(messages, model, body, requestBaseURL(c))
		request.ResponseFormat = "b64_json"
		results, err := h.service.Images(c.Request.Context(), request, callLog)
		if err != nil {
			writeImageError(c, err)
			return
		}
		output := make([]gin.H, 0, len(results))
		for _, result := range results {
			output = append(output, gin.H{"id": service.NewID("ig_"), "type": "image_generation_call", "status": "completed", "result": result.B64, "revised_prompt": result.RevisedPrompt})
		}
		response := completedResponse(id, model, created, output, service.ImageUsage(request, results), false)
		if stream {
			startSSE(c)
			writeSSE(c, responseCreated(id, model, created))
			for index, item := range output {
				writeSSE(c, gin.H{"type": "response.output_item.done", "output_index": index, "item": item})
			}
			writeSSE(c, gin.H{"type": "response.completed", "response": response})
			c.Writer.WriteString("data: [DONE]\n\n")
			c.Writer.Flush()
			return
		}
		c.JSON(http.StatusOK, response)
		return
	}
	cacheKey := h.service.ProtocolCacheKey("responses", body, messages, stream)
	if stream {
		if !search {
			var cached []gin.H
			if h.service.CachedProtocol(cacheKey, true, &cached) {
				startSSE(c)
				for _, event := range cached {
					writeSSE(c, event)
				}
				c.Writer.WriteString("data: [DONE]\n\n")
				c.Writer.Flush()
				callLog.Save("命中缓存", "success", nil)
				return
			}
		}
		id, created := service.NewID("resp_"), time.Now().Unix()
		itemID := service.NewID("msg_")
		startSSE(c)
		events := []gin.H{}
		emit := func(event gin.H) {
			events = append(events, event)
			writeSSE(c, event)
		}
		emit(responseCreated(id, model, created))
		outputIndex := 0
		searchID := ""
		if search {
			query := protocol.SearchQuery(messages)
			searchID = service.NewID("ws_")
			emit(gin.H{"type": "response.output_item.added", "output_index": 0, "item": webSearchItem(query, searchID, "in_progress")})
			emit(gin.H{"type": "response.web_search_call.in_progress", "output_index": 0, "item_id": searchID})
			emit(gin.H{"type": "response.web_search_call.searching", "output_index": 0, "item_id": searchID})
			outputIndex = 1
		}
		text := strings.Builder{}
		if !functionTools {
			emit(gin.H{"type": "response.output_item.added", "output_index": outputIndex, "item": textOutputItem("", itemID, "in_progress")})
		}
		var err error
		if functionTools {
			var value string
			value, err = h.service.Text(c.Request.Context(), model, messages, thinkingEffort(body), search, nil, callLog)
			text.WriteString(value)
		} else {
			_, err = h.service.Text(c.Request.Context(), model, messages, thinkingEffort(body), search, func(delta string) error {
				text.WriteString(delta)
				emit(gin.H{"type": "response.output_text.delta", "item_id": itemID, "output_index": outputIndex, "content_index": 0, "delta": delta})
				return nil
			}, callLog)
		}
		if err != nil {
			emit(gin.H{"type": "error", "error": gin.H{"message": err.Error()}})
		} else {
			response := responseObject(id, model, created, text.String(), messages)
			items := response["output"].([]any)
			if search {
				query := protocol.SearchQuery(messages)
				searchItem := webSearchItem(query, searchID, "completed")
				emit(gin.H{"type": "response.web_search_call.completed", "output_index": 0, "item_id": searchID})
				emit(gin.H{"type": "response.output_item.done", "output_index": 0, "item": searchItem})
				messageItem := textOutputItem(text.String(), itemID, "completed")
				emit(gin.H{"type": "response.output_text.done", "item_id": itemID, "output_index": 1, "content_index": 0, "text": text.String()})
				emit(gin.H{"type": "response.output_item.done", "output_index": 1, "item": messageItem})
				items = []any{searchItem, messageItem}
				response = completedResponse(id, model, created, items, responseUsage(messages, text.String(), model), false)
			} else if functionTools && len(protocol.ParseToolCalls(text.String())) > 0 {
				for index, item := range items {
					emit(gin.H{"type": "response.output_item.done", "output_index": index, "item": item})
				}
			} else {
				if functionTools {
					emit(gin.H{"type": "response.output_item.added", "output_index": 0, "item": textOutputItem("", itemID, "in_progress")})
					if text.Len() > 0 {
						emit(gin.H{"type": "response.output_text.delta", "item_id": itemID, "output_index": 0, "content_index": 0, "delta": text.String()})
					}
				}
				emit(gin.H{"type": "response.output_text.done", "item_id": itemID, "output_index": 0, "content_index": 0, "text": text.String()})
				item := textOutputItem(text.String(), itemID, "completed")
				emit(gin.H{"type": "response.output_item.done", "output_index": 0, "item": item})
				response = completedResponse(id, model, created, []any{item}, responseUsage(messages, text.String(), model), false)
			}
			emit(gin.H{"type": "response.completed", "response": response})
			if !search {
				h.service.StoreProtocol(cacheKey, true, events)
			}
		}
		c.Writer.WriteString("data: [DONE]\n\n")
		c.Writer.Flush()
		return
	}
	if !search {
		var cached gin.H
		if h.service.CachedProtocol(cacheKey, false, &cached) {
			c.JSON(http.StatusOK, cached)
			callLog.Save("命中缓存", "success", nil)
			return
		}
	}
	id, created := service.NewID("resp_"), time.Now().Unix()
	text, err := h.service.Text(c.Request.Context(), model, messages, thinkingEffort(body), search, nil, callLog)
	if err != nil {
		writeError(c, http.StatusBadGateway, err)
		return
	}
	response := responseObject(id, model, created, text, messages)
	if search {
		query := protocol.SearchQuery(messages)
		response = completedResponse(id, model, created, []any{webSearchItem(query, service.NewID("ws_"), "completed"), textOutputItem(text, service.NewID("msg_"), "completed")}, responseUsage(messages, text, model), false)
	} else {
		h.service.StoreProtocol(cacheKey, false, response)
	}
	c.JSON(http.StatusOK, response)
}

func (h *AIHandler) messages(c *gin.Context) {
	var body map[string]any
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	model, _ := body["model"].(string)
	if model == "" {
		model = "auto"
	}
	messages := protocol.AnthropicMessages(body["messages"], body["system"])
	if err := decodeMessageImages(c.Request.Context(), messages); err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	messages = h.service.PrepareMessages(messages)
	messages = protocol.WithToolPrompt(messages, body["tools"], body["tool_choice"])
	stream, _ := body["stream"].(bool)
	id := service.NewID("msg_")
	requestData, _ := json.Marshal(messages)
	callLog := h.logs.NewCallLog(identity(c), c.Request.URL.Path, model, "Messages", string(requestData), time.Now())
	if stream {
		startSSE(c)
		writeAnthropic(c, "message_start", gin.H{"type": "message_start", "message": gin.H{"id": id, "type": "message", "role": "assistant", "content": []any{}, "model": model, "stop_reason": nil, "usage": gin.H{"input_tokens": service.CountMessageTokens(messages, model), "output_tokens": 0}}})
		if hasFunctionTools(body["tools"]) {
			text, err := h.service.Text(c.Request.Context(), model, messages, thinkingEffort(body), false, nil, callLog)
			if err != nil {
				writeAnthropic(c, "error", gin.H{"type": "error", "error": gin.H{"type": "upstream_error", "message": err.Error()}})
				return
			}
			index := 0
			visible := protocol.VisibleToolText(text)
			if visible != "" {
				writeAnthropic(c, "content_block_start", gin.H{"type": "content_block_start", "index": index, "content_block": gin.H{"type": "text", "text": ""}})
				writeAnthropic(c, "content_block_delta", gin.H{"type": "content_block_delta", "index": index, "delta": gin.H{"type": "text_delta", "text": visible}})
				writeAnthropic(c, "content_block_stop", gin.H{"type": "content_block_stop", "index": index})
				index++
			}
			calls := protocol.ParseToolCalls(text)
			for _, call := range calls {
				writeAnthropic(c, "content_block_start", gin.H{"type": "content_block_start", "index": index, "content_block": gin.H{"type": "tool_use", "id": service.NewID("toolu_"), "name": call.Name, "input": gin.H{}}})
				arguments, _ := json.Marshal(call.Arguments)
				writeAnthropic(c, "content_block_delta", gin.H{"type": "content_block_delta", "index": index, "delta": gin.H{"type": "input_json_delta", "partial_json": string(arguments)}})
				writeAnthropic(c, "content_block_stop", gin.H{"type": "content_block_stop", "index": index})
				index++
			}
			reason := "end_turn"
			if len(calls) > 0 {
				reason = "tool_use"
			}
			writeAnthropic(c, "message_delta", gin.H{"type": "message_delta", "delta": gin.H{"stop_reason": reason, "stop_sequence": nil}, "usage": gin.H{"output_tokens": service.CountTextTokens(text, model)}})
			writeAnthropic(c, "message_stop", gin.H{"type": "message_stop"})
			return
		}
		writeAnthropic(c, "content_block_start", gin.H{"type": "content_block_start", "index": 0, "content_block": gin.H{"type": "text", "text": ""}})
		output := strings.Builder{}
		_, err := h.service.Text(c.Request.Context(), model, messages, thinkingEffort(body), false, func(delta string) error {
			output.WriteString(delta)
			writeAnthropic(c, "content_block_delta", gin.H{"type": "content_block_delta", "index": 0, "delta": gin.H{"type": "text_delta", "text": delta}})
			return nil
		}, callLog)
		if err != nil {
			writeAnthropic(c, "error", gin.H{"type": "error", "error": gin.H{"type": "upstream_error", "message": err.Error()}})
		} else {
			writeAnthropic(c, "content_block_stop", gin.H{"type": "content_block_stop", "index": 0})
			writeAnthropic(c, "message_delta", gin.H{"type": "message_delta", "delta": gin.H{"stop_reason": "end_turn", "stop_sequence": nil}, "usage": gin.H{"output_tokens": service.CountTextTokens(output.String(), model)}})
			writeAnthropic(c, "message_stop", gin.H{"type": "message_stop"})
		}
		return
	}
	text, err := h.service.Text(c.Request.Context(), model, messages, thinkingEffort(body), false, nil, callLog)
	if err != nil {
		writeError(c, http.StatusBadGateway, err)
		return
	}
	content := []any{gin.H{"type": "text", "text": protocol.VisibleToolText(text)}}
	stop := "end_turn"
	for _, call := range protocol.ParseToolCalls(text) {
		content = append(content, gin.H{"type": "tool_use", "id": service.NewID("toolu_"), "name": call.Name, "input": call.Arguments})
		stop = "tool_use"
	}
	c.JSON(http.StatusOK, gin.H{"id": id, "type": "message", "role": "assistant", "content": content, "model": model, "stop_reason": stop, "stop_sequence": nil, "usage": gin.H{"input_tokens": service.CountMessageTokens(messages, model), "output_tokens": service.CountTextTokens(text, model)}})
}

func (h *AIHandler) images(c *gin.Context) {
	request, err := parseImageRequest(c)
	if err != nil {
		writeError(c, http.StatusBadRequest, err)
		return
	}
	summary := "文生图"
	if strings.HasSuffix(c.Request.URL.Path, "/edits") {
		summary = "图生图"
	}
	callLog := h.logs.NewCallLog(identity(c), c.Request.URL.Path, request.Model, summary, request.Prompt, time.Now())
	results, err := h.service.Images(c.Request.Context(), request, callLog)
	if err != nil {
		writeImageError(c, err)
		return
	}
	data := make([]gin.H, 0, len(results))
	for _, result := range results {
		item := gin.H{"revised_prompt": result.RevisedPrompt}
		if request.ResponseFormat == "url" {
			item["url"] = result.URL
		} else {
			item["b64_json"] = result.B64
		}
		data = append(data, item)
	}
	response := gin.H{"created": time.Now().Unix(), "data": data, "usage": service.ImageUsage(request, results)}
	if request.Stream {
		startSSE(c)
		response["object"] = "image.generation.result"
		response["model"] = request.Model
		writeSSE(c, response)
		c.Writer.WriteString("data: [DONE]\n\n")
		c.Writer.Flush()
		return
	}
	c.JSON(http.StatusOK, response)
}

func parseImageRequest(c *gin.Context) (service.ImageRequest, error) {
	result := service.ImageRequest{Count: 1, Quality: "auto", ResponseFormat: "b64_json", BaseURL: requestBaseURL(c)}
	if strings.HasPrefix(c.GetHeader("Content-Type"), "multipart/form-data") {
		if err := c.Request.ParseMultipartForm(0); err != nil {
			return result, err
		}
		result.Prompt, result.Model, result.Size, result.Quality, result.ResponseFormat = c.PostForm("prompt"), c.DefaultPostForm("model", result.Model), c.PostForm("size"), c.DefaultPostForm("quality", result.Quality), c.DefaultPostForm("response_format", result.ResponseFormat)
		count, err := strconv.Atoi(c.DefaultPostForm("n", "1"))
		if err != nil {
			return result, errors.New("n must be an integer")
		}
		result.Count = count
		result.Stream, err = strconv.ParseBool(c.DefaultPostForm("stream", "false"))
		if err != nil {
			return result, errors.New("stream must be a boolean")
		}
		if value := c.PostForm("history_id"); value != "" {
			id, err := strconv.ParseInt(value, 10, 64)
			if err != nil {
				return result, err
			}
			result.HistoryID = &id
		}
		if value := c.PostForm("turn_id"); value != "" {
			id, err := strconv.ParseInt(value, 10, 64)
			if err != nil {
				return result, err
			}
			result.TurnID = &id
		}
		for _, key := range []string{"image", "image[]", "images", "images[]", "image_url", "image_url[]"} {
			for _, header := range c.Request.MultipartForm.File[key] {
				file, err := header.Open()
				if err != nil {
					return result, err
				}
				data, err := io.ReadAll(file)
				file.Close()
				if err != nil {
					return result, err
				}
				if len(data) == 0 {
					return result, errors.New("image file is empty")
				}
				mimeType := header.Header.Get("Content-Type")
				if mimeType == "" {
					mimeType = http.DetectContentType(data)
				}
				result.Images = append(result.Images, data)
				result.ImageNames = append(result.ImageNames, header.Filename)
				result.ImageMIMEs = append(result.ImageMIMEs, mimeType)
			}
			for _, value := range c.Request.MultipartForm.Value[key] {
				for _, reference := range imageReferences(value) {
					image, err := decodeImage(c.Request.Context(), reference)
					if err != nil {
						return result, err
					}
					appendImage(&result.Images, &result.ImageNames, &result.ImageMIMEs, image)
				}
			}
		}
		for _, key := range []string{"mask", "mask[]"} {
			for _, header := range c.Request.MultipartForm.File[key] {
				file, err := header.Open()
				if err != nil {
					return result, err
				}
				data, err := io.ReadAll(file)
				file.Close()
				if err != nil {
					return result, err
				}
				if len(data) == 0 {
					return result, errors.New("image file is empty")
				}
				mimeType := header.Header.Get("Content-Type")
				if mimeType == "" {
					mimeType = http.DetectContentType(data)
				}
				result.Masks = append(result.Masks, data)
				result.MaskNames = append(result.MaskNames, header.Filename)
				result.MaskMIMEs = append(result.MaskMIMEs, mimeType)
			}
			for _, value := range c.Request.MultipartForm.Value[key] {
				for _, reference := range imageReferences(value) {
					image, err := decodeImage(c.Request.Context(), reference)
					if err != nil {
						return result, err
					}
					appendImage(&result.Masks, &result.MaskNames, &result.MaskMIMEs, image)
				}
			}
		}
		return validateImageRequest(c, result)
	}
	var body map[string]any
	if err := c.ShouldBindJSON(&body); err != nil {
		return result, err
	}
	if value, ok := body["prompt"].(string); ok {
		result.Prompt = value
	}
	if value, ok := body["model"].(string); ok && value != "" {
		result.Model = value
	}
	if value, ok := body["size"].(string); ok {
		result.Size = value
	}
	if value, ok := body["quality"].(string); ok && value != "" {
		result.Quality = value
	}
	if value, ok := body["response_format"].(string); ok && value != "" {
		result.ResponseFormat = value
	}
	if value, ok := body["n"].(float64); ok && value != 0 {
		result.Count = int(value)
	}
	if value, ok := body["history_id"].(float64); ok {
		id := int64(value)
		result.HistoryID = &id
	}
	if value, ok := body["turn_id"].(float64); ok {
		id := int64(value)
		result.TurnID = &id
	}
	result.Stream, _ = body["stream"].(bool)
	for _, key := range []string{"images", "image", "image_url"} {
		for _, reference := range imageReferences(body[key]) {
			image, err := decodeImage(c.Request.Context(), reference)
			if err != nil {
				return result, err
			}
			appendImage(&result.Images, &result.ImageNames, &result.ImageMIMEs, image)
		}
	}
	for _, reference := range imageReferences(body["mask"]) {
		image, err := decodeImage(c.Request.Context(), reference)
		if err != nil {
			return result, err
		}
		appendImage(&result.Masks, &result.MaskNames, &result.MaskMIMEs, image)
	}
	return validateImageRequest(c, result)
}
func validateImageRequest(c *gin.Context, result service.ImageRequest) (service.ImageRequest, error) {
	if result.Prompt == "" {
		return result, errors.New("prompt is required")
	}
	if result.Count < 1 || result.Count > 4 {
		return result, errors.New("n must be between 1 and 4")
	}
	if strings.HasSuffix(c.Request.URL.Path, "/edits") && len(result.Images) == 0 {
		return result, errors.New("image file or image_url is required")
	}
	return result, nil
}

func mapMessages(value any) []map[string]any {
	raw, _ := value.([]any)
	result := make([]map[string]any, 0, len(raw))
	for _, item := range raw {
		if message, ok := item.(map[string]any); ok {
			result = append(result, message)
		}
	}
	return result
}
func thinkingEffort(body map[string]any) string {
	if value, ok := body["thinking_effort"].(string); ok {
		return value
	}
	if value, ok := body["reasoning_effort"].(string); ok {
		return value
	}
	if reasoning, ok := body["reasoning"].(map[string]any); ok {
		value, _ := reasoning["effort"].(string)
		return value
	}
	return ""
}
func responseObject(id string, model string, created int64, text string, messages []map[string]any) gin.H {
	output := []any{}
	calls := protocol.ParseToolCalls(text)
	if len(calls) > 0 {
		for _, call := range calls {
			arguments, _ := json.Marshal(call.Arguments)
			output = append(output, gin.H{"type": "function_call", "id": service.NewID("fc_"), "call_id": service.NewID("call_"), "name": call.Name, "arguments": string(arguments), "status": "completed"})
		}
	} else {
		output = append(output, gin.H{"id": id + "_message", "type": "message", "status": "completed", "role": "assistant", "content": []any{gin.H{"type": "output_text", "text": text, "annotations": []any{}}}})
	}
	return gin.H{"id": id, "object": "response", "created_at": created, "status": "completed", "error": nil, "incomplete_details": nil, "model": model, "output": output, "parallel_tool_calls": len(calls) > 0, "usage": service.TokenUsage(service.CountMessageTextTokens(messages, model), service.CountMessageImageTokens(messages), service.CountTextTokens(text, model), 0)}
}
func responseCreated(id string, model string, created int64) gin.H {
	return gin.H{"type": "response.created", "response": gin.H{"id": id, "object": "response", "created_at": created, "status": "in_progress", "error": nil, "incomplete_details": nil, "model": model, "output": []any{}, "parallel_tool_calls": false}}
}
func completedResponse(id string, model string, created int64, output any, usage any, parallel bool) gin.H {
	return gin.H{"id": id, "object": "response", "created_at": created, "status": "completed", "error": nil, "incomplete_details": nil, "model": model, "output": output, "parallel_tool_calls": parallel, "usage": usage}
}
func textOutputItem(text string, id string, status string) gin.H {
	return gin.H{"id": id, "type": "message", "status": status, "role": "assistant", "content": []any{gin.H{"type": "output_text", "text": text, "annotations": []any{}}}}
}
func webSearchItem(query string, id string, status string) gin.H {
	return gin.H{"id": id, "type": "web_search_call", "status": status, "action": gin.H{"type": "search", "query": query, "queries": []string{query}}}
}
func responseUsage(messages []map[string]any, text string, model string) map[string]any {
	return service.TokenUsage(service.CountMessageTextTokens(messages, model), service.CountMessageImageTokens(messages), service.CountTextTokens(text, model), 0)
}
func startSSE(c *gin.Context) {
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("X-Accel-Buffering", "no")
	c.Status(http.StatusOK)
	c.Writer.WriteString(": stream-open\n\n")
	c.Writer.Flush()
}
func writeSSE(c *gin.Context, value any) {
	data, _ := json.Marshal(value)
	c.Writer.WriteString("data: " + string(data) + "\n\n")
	c.Writer.Flush()
}
func writeAnthropic(c *gin.Context, event string, value any) {
	data, _ := json.Marshal(value)
	c.Writer.WriteString("event: " + event + "\ndata: " + string(data) + "\n\n")
	c.Writer.Flush()
}

type imageReference struct {
	Value string
	Name  string
	MIME  string
}
type decodedImage struct {
	Data []byte
	Name string
	MIME string
}

func imageReferences(value any) []imageReference {
	switch item := value.(type) {
	case string:
		if strings.HasPrefix(item, "[") || strings.HasPrefix(item, "{") {
			var parsed any
			if json.Unmarshal([]byte(item), &parsed) == nil {
				return imageReferences(parsed)
			}
		}
		return []imageReference{{Value: item}}
	case map[string]any:
		name, _ := item["filename"].(string)
		if name == "" {
			name, _ = item["file_name"].(string)
		}
		mimeType, _ := item["mime_type"].(string)
		if mimeType == "" {
			mimeType, _ = item["mimeType"].(string)
		}
		if nested, ok := item["image_url"].(map[string]any); ok {
			result := imageReferences(nested["url"])
			for index := range result {
				result[index].Name, result[index].MIME = name, mimeType
			}
			return result
		}
		for _, key := range []string{"image_url", "url", "b64_json", "base64"} {
			if value, ok := item[key].(string); ok {
				return []imageReference{{Value: value, Name: name, MIME: mimeType}}
			}
		}
	case []any:
		result := []imageReference{}
		for _, raw := range item {
			result = append(result, imageReferences(raw)...)
		}
		return result
	}
	return nil
}
// 图片地址只允许访问公网，拨号时校验解析后的真实地址，重定向和域名解析到内网同样会被拒绝
var imageFetchClient = &http.Client{Timeout: 30 * time.Second, Transport: &http.Transport{DialContext: (&net.Dialer{Timeout: 10 * time.Second, Control: func(network string, address string, conn syscall.RawConn) error {
	host, _, _ := net.SplitHostPort(address)
	ip, _ := netip.ParseAddr(host)
	ip = ip.Unmap()
	if !ip.IsGlobalUnicast() || ip.IsPrivate() {
		return errors.New("image_url must point to a public address")
	}
	return nil
}}).DialContext, TLSHandshakeTimeout: 10 * time.Second}}

func decodeImage(ctx context.Context, reference imageReference) (decodedImage, error) {
	value := reference.Value
	if strings.HasPrefix(value, "http://") || strings.HasPrefix(value, "https://") {
		request, err := http.NewRequestWithContext(ctx, http.MethodGet, value, nil)
		if err != nil {
			return decodedImage{}, err
		}
		request.Header.Set("Accept", "image/*,*/*;q=0.8")
		request.Header.Set("User-Agent", "chatgpt2api image fetcher")
		response, err := imageFetchClient.Do(request)
		if err != nil {
			return decodedImage{}, err
		}
		defer response.Body.Close()
		if response.StatusCode < 200 || response.StatusCode >= 300 {
			return decodedImage{}, errors.New("image_url fetch failed")
		}
		data, err := io.ReadAll(io.LimitReader(response.Body, (50<<20)+1))
		if err != nil {
			return decodedImage{}, err
		}
		if len(data) > 50<<20 {
			return decodedImage{}, errors.New("image URL exceeds 50MB limit")
		}
		if len(data) == 0 {
			return decodedImage{}, errors.New("image_url returned empty content")
		}
		mimeType := response.Header.Get("Content-Type")
		if index := strings.IndexByte(mimeType, ';'); index >= 0 {
			mimeType = mimeType[:index]
		}
		parsed, _ := url.Parse(value)
		if mimeType == "" || mimeType == "application/octet-stream" || mimeType == "binary/octet-stream" {
			mimeType = mime.TypeByExtension(path.Ext(parsed.Path))
			if mimeType == "" {
				mimeType = "image/png"
			}
		}
		if !strings.HasPrefix(mimeType, "image/") {
			return decodedImage{}, errors.New("image_url must point to an image")
		}
		name := reference.Name
		if name == "" {
			name = path.Base(parsed.Path)
			if name == "." || name == "/" || name == "" {
				name = "image_url" + imageExtension(mimeType)
			}
		}
		return decodedImage{Data: data, Name: name, MIME: mimeType}, nil
	}
	if strings.HasPrefix(value, "data:") {
		header, payload, found := strings.Cut(value, ",")
		if !found {
			return decodedImage{}, errors.New("invalid data image URL")
		}
		mimeType := strings.TrimPrefix(strings.Split(header, ";")[0], "data:")
		if mimeType == "" {
			mimeType = "image/png"
		}
		if !strings.HasPrefix(mimeType, "image/") {
			return decodedImage{}, errors.New("image_url must point to an image")
		}
		var data []byte
		var err error
		if strings.Contains(header, ";base64") {
			data, err = base64.StdEncoding.DecodeString(payload)
		} else {
			var decoded string
			decoded, err = url.PathUnescape(payload)
			data = []byte(decoded)
		}
		if err != nil {
			return decodedImage{}, errors.New("invalid data image URL")
		}
		if len(data) > 50<<20 {
			return decodedImage{}, errors.New("image URL exceeds 50MB limit")
		}
		if len(data) == 0 {
			return decodedImage{}, errors.New("image URL is empty")
		}
		name := reference.Name
		if name == "" {
			name = "image_url" + imageExtension(mimeType)
		}
		return decodedImage{Data: data, Name: name, MIME: mimeType}, nil
	}
	data, err := base64.StdEncoding.DecodeString(value)
	if err != nil {
		return decodedImage{}, errors.New("invalid base64 image data")
	}
	if len(data) > 50<<20 {
		return decodedImage{}, errors.New("image URL exceeds 50MB limit")
	}
	if len(data) == 0 {
		return decodedImage{}, errors.New("image file is empty")
	}
	name, mimeType := reference.Name, reference.MIME
	if mimeType == "" {
		mimeType = "image/png"
	}
	if name == "" {
		name = "image.png"
	}
	return decodedImage{Data: data, Name: name, MIME: mimeType}, nil
}
func appendImage(data *[][]byte, names *[]string, mimeTypes *[]string, image decodedImage) {
	*data = append(*data, image.Data)
	*names = append(*names, image.Name)
	*mimeTypes = append(*mimeTypes, image.MIME)
}
func imageExtension(mimeType string) string {
	extensions, _ := mime.ExtensionsByType(mimeType)
	if len(extensions) > 0 {
		return extensions[0]
	}
	return ".png"
}
func hasFunctionTools(value any) bool {
	items, _ := value.([]any)
	for _, raw := range items {
		item, _ := raw.(map[string]any)
		if item["type"] == "function" || item["name"] != nil {
			return true
		}
	}
	return false
}
func openAIToolCalls(calls []protocol.ToolCall) []gin.H {
	result := make([]gin.H, 0, len(calls))
	for index, call := range calls {
		arguments, _ := json.Marshal(call.Arguments)
		result = append(result, gin.H{"index": index, "id": service.NewID("call_"), "type": "function", "function": gin.H{"name": call.Name, "arguments": string(arguments)}})
	}
	return result
}
func decodeMessageImages(ctx context.Context, messages []map[string]any) error {
	for _, message := range messages {
		parts, ok := message["content"].([]any)
		if !ok {
			continue
		}
		for index, raw := range parts {
			part, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			kind, _ := part["type"].(string)
			if kind != "image" && kind != "image_url" && kind != "input_image" {
				continue
			}
			source := part["image_url"]
			if nested, ok := source.(map[string]any); ok {
				source = nested["url"]
			}
			if source == nil {
				source = part["url"]
			}
			mimeType, _ := part["mime"].(string)
			if anthopic, ok := part["source"].(map[string]any); ok {
				source = anthopic["data"]
				if mimeType == "" {
					mimeType, _ = anthopic["media_type"].(string)
				}
			}
			value, ok := source.(string)
			if !ok {
				continue
			}
			name, _ := part["name"].(string)
			image, err := decodeImage(ctx, imageReference{Value: value, Name: name, MIME: mimeType})
			if err != nil {
				return err
			}
			parts[index] = map[string]any{"type": "image", "data": image.Data, "name": image.Name, "mime": image.MIME}
		}
		message["content"] = parts
	}
	return nil
}
func imageRequestFromMessages(messages []map[string]any, model string, body map[string]any, baseURL string) service.ImageRequest {
	prompt := strings.Builder{}
	images := [][]byte{}
	names, mimeTypes := []string{}, []string{}
	for _, message := range messages {
		switch content := message["content"].(type) {
		case string:
			prompt.WriteString(content)
		case []any:
			for _, raw := range content {
				part, _ := raw.(map[string]any)
				if text, ok := part["text"].(string); ok {
					prompt.WriteString(text)
				}
				if data, ok := part["data"].([]byte); ok {
					images = append(images, data)
					names = append(names, imageString(part["name"], "image.png"))
					mimeTypes = append(mimeTypes, imageString(part["mime"], "image/png"))
				}
			}
		}
	}
	count := 1
	if value, ok := body["n"].(float64); ok {
		count = int(value)
	}
	size, _ := body["size"].(string)
	quality, _ := body["quality"].(string)
	if tools, ok := body["tools"].([]any); ok {
		for _, raw := range tools {
			tool, _ := raw.(map[string]any)
			if tool["type"] != "image_generation" {
				continue
			}
			if size == "" {
				size, _ = tool["size"].(string)
			}
			if quality == "" {
				quality, _ = tool["quality"].(string)
			}
			break
		}
	}
	if quality == "" {
		quality = "auto"
	}
	return service.ImageRequest{Prompt: prompt.String(), Model: model, Count: count, Size: size, Quality: quality, ResponseFormat: "url", BaseURL: baseURL, Images: images, ImageNames: names, ImageMIMEs: mimeTypes}
}
func imageString(value any, fallback string) string {
	text, _ := value.(string)
	if text == "" {
		return fallback
	}
	return text
}
func imageMarkdown(results []service.ImageResult) string {
	parts := make([]string, 0, len(results))
	for _, result := range results {
		parts = append(parts, "![Generated Image]("+result.URL+")")
	}
	return strings.Join(parts, "\n")
}
func imageGenerationRequested(value any) bool {
	items, _ := value.([]any)
	for _, raw := range items {
		item, _ := raw.(map[string]any)
		if item["type"] == "image_generation" {
			return true
		}
	}
	return false
}

func imageModalityRequested(value any) bool {
	items, _ := value.([]any)
	for _, item := range items {
		if item == "image" {
			return true
		}
	}
	return false
}

func writeImageError(c *gin.Context, err error) {
	status, errorType, code, param := http.StatusBadGateway, "server_error", "upstream_error", any(nil)
	var imageErr *service.ImageError
	if errors.As(err, &imageErr) {
		if imageErr.Status != 0 {
			status = imageErr.Status
		}
		if imageErr.Type != "" {
			errorType = imageErr.Type
		}
		if imageErr.Code != "" {
			code = imageErr.Code
		}
		param = imageErr.Param
	}
	message := err.Error()
	lower := strings.ToLower(message)
	if code == "upstream_prepare_rejected" {
		message = "The upstream rejected the conversation preparation request. Try again with fewer reference images, or retry later."
	} else if strings.Contains(lower, "backend-api/") || strings.Contains(lower, "status=") || strings.Contains(lower, "body=") || strings.Contains(lower, "chatgpt.com") || strings.Contains(lower, "upstreamhttperror") {
		message = "The image generation request failed. Please try again later."
	}
	c.JSON(status, gin.H{"error": gin.H{"message": message, "type": errorType, "param": param, "code": code}})
}
