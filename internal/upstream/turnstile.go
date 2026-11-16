package upstream

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"reflect"
	"strconv"
	"strings"
	"time"
)

type OrderedMap struct {
	Keys   []string
	Values map[string]any
}

type Turnstile struct{}

func NewOrderedMap() *OrderedMap {
	return &OrderedMap{Values: map[string]any{}}
}

func (m *OrderedMap) Add(key string, value any) {
	if _, exists := m.Values[key]; !exists {
		m.Keys = append(m.Keys, key)
	}
	m.Values[key] = value
}

func (m *OrderedMap) MarshalJSON() ([]byte, error) {
	buffer := bytes.NewBufferString("{")
	for index, key := range m.Keys {
		if index > 0 {
			buffer.WriteByte(',')
		}
		name, _ := json.Marshal(key)
		value, err := json.Marshal(m.Values[key])
		if err != nil {
			return nil, err
		}
		buffer.Write(name)
		buffer.WriteByte(':')
		buffer.Write(value)
	}
	buffer.WriteByte('}')
	return buffer.Bytes(), nil
}

func (Turnstile) ToString(value any) string {
	special := map[string]string{
		"window.Math":            "[object Math]",
		"window.Reflect":         "[object Reflect]",
		"window.performance":     "[object Performance]",
		"window.localStorage":    "[object Storage]",
		"window.Object":          "function Object() { [native code] }",
		"window.Reflect.set":     "function set() { [native code] }",
		"window.performance.now": "function () { [native code] }",
		"window.Object.create":   "function create() { [native code] }",
		"window.Object.keys":     "function keys() { [native code] }",
		"window.Math.random":     "function random() { [native code] }",
	}
	switch item := value.(type) {
	case nil:
		return "undefined"
	case string:
		if result := special[item]; result != "" {
			return result
		}
		return item
	case float64:
		return strconv.FormatFloat(item, 'f', -1, 64)
	case int:
		return strconv.Itoa(item)
	case bool:
		if item {
			return "True"
		}
		return "False"
	case []string:
		return strings.Join(item, ",")
	case *OrderedMap:
		data, _ := json.Marshal(item)
		return string(data)
	default:
		data, _ := json.Marshal(item)
		return string(data)
	}
}

func (Turnstile) XORString(value string, key string) string {
	if key == "" {
		return value
	}
	source, secret := []rune(value), []rune(key)
	for index := range source {
		source[index] ^= secret[index%len(secret)]
	}
	return string(source)
}

func (t Turnstile) Solve(dx string, pToken string) string {
	decoded, err := base64.StdEncoding.DecodeString(dx)
	if err != nil {
		return ""
	}
	var tokens [][]any
	if json.Unmarshal([]byte(t.XORString(string(decoded), pToken)), &tokens) != nil {
		return ""
	}
	values := map[int]any{1: 1, 2: 2, 3: 3, 5: 5, 6: 6, 7: 7, 8: 8, 9: tokens, 10: "window", 14: 14, 15: 15, 16: pToken, 17: 17, 18: 18, 19: 19, 20: 20, 21: 21, 23: 23, 24: 24}
	result := ""
	started := time.Now()
	for _, token := range tokens {
		func() {
			defer func() { recover() }()
			t.run(token, values, &result, started)
		}()
	}
	return result
}

func (t Turnstile) run(token []any, values map[int]any, result *string, started time.Time) {
	if len(token) == 0 {
		return
	}
	opcode := int(token[0].(float64))
	number := func(index int) int { return int(token[index].(float64)) }
	invoke := func(target any, args []any) {
		code, ok := target.(int)
		if !ok {
			return
		}
		call := make([]any, 1, len(args)+1)
		call[0] = float64(code)
		call = append(call, args...)
		t.run(call, values, result, started)
	}
	switch opcode {
	case 1:
		values[number(1)] = t.XORString(t.ToString(values[number(1)]), t.ToString(values[number(2)]))
	case 2:
		values[number(1)] = token[2]
	case 3:
		*result = base64.StdEncoding.EncodeToString([]byte(t.ToString(values[number(1)])))
	case 5:
		current, incoming := values[number(1)], values[number(2)]
		if list, ok := current.([]any); ok {
			values[number(1)] = append(list, incoming)
		} else if isStringOrNumber(current) || isStringOrNumber(incoming) {
			values[number(1)] = t.ToString(current) + t.ToString(incoming)
		} else {
			values[number(1)] = "NaN"
		}
	case 6:
		current, first := values[number(2)].(string)
		incoming, second := values[number(3)].(string)
		if first && second {
			value := current + "." + incoming
			if value == "window.document.location" {
				value = "https://chatgpt.com/"
			}
			values[number(1)] = value
		}
	case 7:
		target := values[number(1)]
		args := dereference(token[2:], values)
		if target == "window.Reflect.set" && len(args) == 3 {
			if object, ok := args[0].(*OrderedMap); ok {
				object.Add(t.ToString(args[1]), args[2])
			}
		} else {
			invoke(target, args)
		}
	case 8:
		values[number(1)] = values[number(2)]
	case 14:
		var value any
		if json.Unmarshal([]byte(t.ToString(values[number(2)])), &value) == nil {
			values[number(1)] = value
		}
	case 15:
		data, _ := json.Marshal(values[number(2)])
		values[number(1)] = string(data)
	case 17:
		target := values[number(2)]
		args := dereference(token[3:], values)
		switch target {
		case "window.performance.now":
			values[number(1)] = float64(time.Since(started).Nanoseconds())/1e6 + randomFloat()
		case "window.Object.create":
			values[number(1)] = NewOrderedMap()
		case "window.Object.keys":
			if len(args) > 0 && args[0] == "window.localStorage" {
				values[number(1)] = []string{"STATSIG_LOCAL_STORAGE_INTERNAL_STORE_V4", "STATSIG_LOCAL_STORAGE_STABLE_ID", "client-correlated-secret", "oai/apps/capExpiresAt", "oai-did", "STATSIG_LOCAL_STORAGE_LOGGING_REQUEST", "UiState.isNavigationCollapsed.1"}
			}
		case "window.Math.random":
			values[number(1)] = randomFloat()
		default:
			invoke(target, args)
		}
	case 18:
		data, _ := base64.StdEncoding.DecodeString(t.ToString(values[number(1)]))
		values[number(1)] = string(data)
	case 19:
		values[number(1)] = base64.StdEncoding.EncodeToString([]byte(t.ToString(values[number(1)])))
	case 20:
		if reflect.DeepEqual(values[number(1)], values[number(2)]) {
			invoke(values[number(3)], dereference(token[4:], values))
		}
	case 21:
		return
	case 23:
		if values[number(1)] != nil {
			invoke(values[number(2)], token[3:])
		}
	case 24:
		current, first := values[number(2)].(string)
		incoming, second := values[number(3)].(string)
		if first && second {
			values[number(1)] = current + "." + incoming
		}
	}
}

func dereference(indexes []any, values map[int]any) []any {
	result := make([]any, 0, len(indexes))
	for _, index := range indexes {
		result = append(result, values[int(index.(float64))])
	}
	return result
}

func isStringOrNumber(value any) bool {
	switch value.(type) {
	case string, float64, int:
		return true
	}
	return false
}
