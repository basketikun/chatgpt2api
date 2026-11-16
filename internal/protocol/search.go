package protocol

import (
	"regexp"
	"strings"
	"unicode/utf8"
)

var searchAnnotationPattern = regexp.MustCompile("\ue200([^\ue201]*)\ue201")
var unfinishedSearchAnnotationPattern = regexp.MustCompile("\ue200[^\ue201]*$")
var searchPunctuationPattern = regexp.MustCompile(`\s+([.,;:!?。，；：！？、])`)
var digitsPattern = regexp.MustCompile(`^\d+$`)
var searchURLPattern = regexp.MustCompile(`https?://[^\s)]+`)

func CleanSearchText(text string) string {
	text = searchAnnotationPattern.ReplaceAllStringFunc(text, func(annotation string) string {
		parts := strings.Split(strings.TrimSuffix(strings.TrimPrefix(annotation, "\ue200"), "\ue201"), "\ue202")
		kind := ""
		if len(parts) > 0 {
			kind = strings.ToLower(strings.TrimSpace(parts[0]))
			parts = parts[1:]
		}
		for index := range parts {
			parts[index] = strings.TrimSpace(parts[index])
		}
		if kind == "url" {
			label, link := "", ""
			if len(parts) > 0 {
				label = parts[0]
			}
			if len(parts) > 1 {
				link = parts[1]
			}
			if label != "" && (strings.HasPrefix(link, "http://") || strings.HasPrefix(link, "https://")) {
				return label + " (" + link + ")"
			}
			if label != "" {
				return label
			}
			return link
		}
		for _, part := range parts {
			lower := strings.ToLower(part)
			if part != "" && !strings.HasPrefix(lower, "turn") && !strings.HasPrefix(lower, "source") && !digitsPattern.MatchString(part) {
				return part
			}
		}
		return ""
	})
	text = unfinishedSearchAnnotationPattern.ReplaceAllString(text, "")
	return strings.TrimSpace(searchPunctuationPattern.ReplaceAllString(text, "$1"))
}

func SearchAnnotations(text string) []map[string]any {
	result := []map[string]any{}
	for _, indexes := range searchURLPattern.FindAllStringIndex(text, -1) {
		link := text[indexes[0]:indexes[1]]
		result = append(result, map[string]any{"start_index": utf8.RuneCountInString(text[:indexes[0]]), "end_index": utf8.RuneCountInString(text[:indexes[1]]), "url": link, "title": link})
	}
	return result
}
