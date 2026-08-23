# JSON Format Repair Task

You are a JSON format repair expert. The following JSON string has formatting errors and cannot be parsed correctly.

## Error Information
- **Error Message**: {error_message}

## Malformed JSON Content
```
{malformed_json}
```

## Your Task
Please fix the JSON format errors and return a valid JSON object. Common issues include:
1. Missing closing brackets `}` or `]`
2. Extra commas at the end of arrays or objects
3. Unescaped special characters in strings
4. Missing quotes around keys or string values
5. Truncated content (incomplete JSON)
6. Invalid escape sequences

## Requirements
1. **ONLY output the corrected JSON**, no explanations or additional text
2. Preserve as much of the original content as possible
3. If the JSON is severely truncated, complete the structure with reasonable default values (empty strings `""` for missing string fields, empty objects `{}` for missing object fields)
4. Ensure all brackets are properly matched
5. Ensure all strings are properly quoted and escaped

## Output
Return ONLY the valid JSON object, nothing else.