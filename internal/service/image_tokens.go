package service

import (
	"bytes"
	"encoding/base64"
	"fmt"
	"math"
	"regexp"
	"strconv"
	"strings"

	"github.com/disintegration/imaging"
	"github.com/tiktoken-go/tokenizer"
	_ "golang.org/x/image/webp"
)

var imageSizePattern = regexp.MustCompile(`(\d{2,5})\D+(\d{2,5})`)

func imageTaskUsage(request ImageRequest, results []ImageResult) (int, int, int) {
	usage := ImageUsage(request, results)
	return usage["input_tokens"].(int), usage["output_tokens"].(int), usage["total_tokens"].(int)
}

func ImageUsage(request ImageRequest, results []ImageResult) map[string]any {
	inputText := CountTextTokens(request.Prompt, request.Model)
	inputImages := 0
	for _, data := range request.Images {
		if width, height, ok := imageDimensions(data); ok {
			inputImages += countImageInputTokens(width, height)
		}
	}
	fallbackWidth, fallbackHeight := parseImageSize(request.Size)
	output := 0
	for _, result := range results {
		width, height := fallbackWidth, fallbackHeight
		if data, err := base64.StdEncoding.DecodeString(result.B64); err == nil {
			if resultWidth, resultHeight, ok := imageDimensions(data); ok {
				width, height = resultWidth, resultHeight
			}
		}
		output += countGeneratedImageTokens(width, height, request.Quality)
	}
	return TokenUsage(inputText, inputImages, 0, output)
}

func CountTextTokens(text string, model string) int {
	codec, err := tokenizer.ForModel(tokenizer.Model(model))
	if err != nil {
		codec, err = tokenizer.Get(tokenizer.O200kBase)
	}
	if err != nil {
		codec, err = tokenizer.Get(tokenizer.Cl100kBase)
	}
	if err != nil {
		return 0
	}
	count, _ := codec.Count(text)
	return count
}

func CountMessageTextTokens(messages []map[string]any, model string) int {
	total := 0
	for _, message := range messages {
		total += 3
		for key, value := range message {
			text := ""
			if key == "content" {
				text = messageText(value)
			} else if value, ok := value.(string); ok {
				text = value
			}
			if text != "" {
				total += CountTextTokens(text, model)
			}
			if key == "name" {
				total++
			}
		}
	}
	return total + 3
}

func CountMessageImageTokens(messages []map[string]any) int {
	total := 0
	for _, message := range messages {
		parts, _ := message["content"].([]any)
		for _, raw := range parts {
			part, _ := raw.(map[string]any)
			data, _ := part["data"].([]byte)
			if width, height, ok := imageDimensions(data); ok {
				total += countImageInputTokens(width, height)
			}
		}
	}
	return total
}

func CountMessageTokens(messages []map[string]any, model string) int {
	return CountMessageTextTokens(messages, model) + CountMessageImageTokens(messages)
}

func CompletionUsage(messages []map[string]any, output string, model string) map[string]any {
	inputText, inputImages := CountMessageTextTokens(messages, model), CountMessageImageTokens(messages)
	outputText := CountTextTokens(output, model)
	return map[string]any{
		"prompt_tokens": inputText + inputImages, "completion_tokens": outputText, "total_tokens": inputText + inputImages + outputText,
		"prompt_tokens_details":     map[string]any{"text_tokens": inputText, "image_tokens": inputImages, "cached_tokens": 0, "audio_tokens": 0},
		"completion_tokens_details": map[string]any{"text_tokens": outputText, "image_tokens": 0, "reasoning_tokens": 0, "audio_tokens": 0, "accepted_prediction_tokens": 0, "rejected_prediction_tokens": 0},
	}
}

func ChatImageUsage(request ImageRequest, results []ImageResult) map[string]any {
	usage := ImageUsage(request, results)
	inputDetails := usage["input_tokens_details"].(map[string]any)
	outputDetails := usage["output_tokens_details"].(map[string]any)
	return map[string]any{
		"prompt_tokens": usage["input_tokens"], "completion_tokens": usage["output_tokens"], "total_tokens": usage["total_tokens"],
		"prompt_tokens_details":     map[string]any{"text_tokens": inputDetails["text_tokens"], "image_tokens": inputDetails["image_tokens"], "cached_tokens": 0, "audio_tokens": 0},
		"completion_tokens_details": map[string]any{"text_tokens": 0, "image_tokens": outputDetails["image_tokens"], "reasoning_tokens": 0, "audio_tokens": 0, "accepted_prediction_tokens": 0, "rejected_prediction_tokens": 0},
	}
}

func TokenUsage(inputText int, inputImages int, outputText int, outputImages int) map[string]any {
	input, output := inputText+inputImages, outputText+outputImages
	return map[string]any{
		"input_tokens": input, "output_tokens": output, "total_tokens": input + output,
		"input_tokens_details":  map[string]any{"text_tokens": inputText, "image_tokens": inputImages, "cached_tokens": 0},
		"output_tokens_details": map[string]any{"text_tokens": outputText, "image_tokens": outputImages, "reasoning_tokens": 0},
	}
}

func messageText(value any) string {
	if text, ok := value.(string); ok {
		return text
	}
	parts, _ := value.([]any)
	result := strings.Builder{}
	for _, raw := range parts {
		part, _ := raw.(map[string]any)
		kind := fmt.Sprint(part["type"])
		if kind == "text" || kind == "input_text" || kind == "output_text" {
			result.WriteString(fmt.Sprint(part["text"]))
		}
	}
	return result.String()
}

func imageDimensions(data []byte) (int, int, bool) {
	value, err := imaging.Decode(bytes.NewReader(data))
	if err != nil {
		return 0, 0, false
	}
	bounds := value.Bounds()
	return bounds.Dx(), bounds.Dy(), bounds.Dx() > 0 && bounds.Dy() > 0
}

func countImageInputTokens(width int, height int) int {
	resizedWidth, resizedHeight := float64(width), float64(height)
	scale := math.Min(1, 2048/math.Max(resizedWidth, resizedHeight))
	resizedWidth *= scale
	resizedHeight *= scale
	if imagePatchCount(resizedWidth, resizedHeight) > 1536 {
		shrink := math.Sqrt(32 * 32 * 1536 / (resizedWidth * resizedHeight))
		widthUnits, heightUnits := resizedWidth*shrink/32, resizedHeight*shrink/32
		shrink *= math.Min(math.Floor(widthUnits)/widthUnits, math.Floor(heightUnits)/heightUnits)
		resizedWidth *= shrink
		resizedHeight *= shrink
	}
	return int(math.Ceil(math.Min(float64(imagePatchCount(math.Max(1, resizedWidth), math.Max(1, resizedHeight))), 1536) * 1.62))
}

func countGeneratedImageTokens(width int, height int, quality string) int {
	patches := float64(imagePatchCount(float64(width), float64(height)))
	switch quality {
	case "low":
		return int(math.Ceil(patches * 17 / 64))
	case "high", "hd":
		return int(math.Ceil(patches * 65 / 16))
	default:
		return int(math.Ceil(patches * 33 / 32))
	}
}

func imagePatchCount(width float64, height float64) int {
	return int(math.Ceil(width/32) * math.Ceil(height/32))
}

func parseImageSize(value string) (int, int) {
	match := imageSizePattern.FindStringSubmatch(value)
	if len(match) != 3 {
		return 1024, 1024
	}
	width, _ := strconv.Atoi(match[1])
	height, _ := strconv.Atoi(match[2])
	if width <= 0 || height <= 0 {
		return 1024, 1024
	}
	return width, height
}
