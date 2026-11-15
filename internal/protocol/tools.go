package protocol

import (
	"encoding/json"
	"encoding/xml"
	"fmt"
	"strings"
)

type ToolCall struct {
	Name      string
	Arguments map[string]any
}
type toolXMLCall struct {
	ToolName   string            `xml:"tool_name"`
	Name       string            `xml:"name"`
	Function   string            `xml:"function"`
	Parameters toolXMLParameters `xml:"parameters"`
	Input      toolXMLParameters `xml:"input"`
	Arguments  toolXMLParameters `xml:"arguments"`
}
type toolXMLParameters struct {
	Text   string             `xml:",chardata"`
	Values []toolXMLParameter `xml:",any"`
}
type toolXMLParameter struct {
	XMLName xml.Name
	Text    string `xml:",chardata"`
}

func WithToolPrompt(messages []map[string]any, tools any, choice any) []map[string]any {
	items, ok := tools.([]any)
	if !ok || len(items) == 0 {
		return messages
	}
	blocks := strings.Builder{}
	for _, raw := range items {
		tool, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		function, _ := tool["function"].(map[string]any)
		name := fmt.Sprint(function["name"])
		if name == "<nil>" {
			name = fmt.Sprint(tool["name"])
		}
		if name == "" || name == "<nil>" {
			continue
		}
		schema := function["parameters"]
		if schema == nil {
			schema = tool["parameters"]
		}
		if schema == nil {
			schema = tool["input_schema"]
		}
		description := function["description"]
		if description == nil {
			description = tool["description"]
		}
		encoded, _ := json.Marshal(schema)
		blocks.WriteString("Tool: " + name + "\nDescription: " + fmt.Sprint(description) + "\nParameters: " + string(encoded) + "\n")
	}
	if blocks.Len() == 0 {
		return messages
	}
	required := choice == "any" || choice == "tool" || choice == "function" || choice == "required"
	if value, ok := choice.(map[string]any); ok {
		switch value["type"] {
		case "any", "tool", "function", "required":
			required = true
		}
	}
	requirement := "Use a provided tool whenever it matches the request."
	if required {
		requirement = "You must call one or more provided tools."
	}
	prompt := "The client provides these tools:\n" + blocks.String() + requirement + "\nTo call tools, output only: <tool_calls><tool_call><tool_name>NAME</tool_name><parameters><PARAM>VALUE</PARAM></parameters></tool_call></tool_calls>"
	return append([]map[string]any{{"role": "system", "content": prompt}}, messages...)
}

func ParseToolCalls(text string) []ToolCall {
	decoder := xml.NewDecoder(strings.NewReader(text))
	result := []ToolCall{}
	for {
		token, err := decoder.Token()
		if err != nil {
			break
		}
		start, ok := token.(xml.StartElement)
		if !ok || start.Name.Local != "tool_call" && start.Name.Local != "function_call" && start.Name.Local != "invoke" {
			continue
		}
		raw := toolXMLCall{}
		if decoder.DecodeElement(&raw, &start) != nil {
			continue
		}
		name := raw.ToolName
		if name == "" {
			name = raw.Name
		}
		if name == "" {
			name = raw.Function
		}
		if name == "" {
			continue
		}
		parameters := raw.Parameters
		if parameters.Text == "" && len(parameters.Values) == 0 {
			parameters = raw.Input
		}
		if parameters.Text == "" && len(parameters.Values) == 0 {
			parameters = raw.Arguments
		}
		arguments := map[string]any{}
		if json.Unmarshal([]byte(parameters.Text), &arguments) != nil {
			for _, parameter := range parameters.Values {
				var value any
				if json.Unmarshal([]byte(parameter.Text), &value) != nil {
					value = parameter.Text
				}
				arguments[parameter.XMLName.Local] = value
			}
		}
		result = append(result, ToolCall{Name: name, Arguments: arguments})
	}
	return result
}
func VisibleToolText(text string) string {
	if index := strings.Index(text, "<tool_calls"); index >= 0 {
		return text[:index]
	}
	return text
}
