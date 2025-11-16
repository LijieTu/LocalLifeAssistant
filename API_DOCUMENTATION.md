# 🎉 Local Life Assistant - Event API Documentation

## Overview

The Local Life Assistant Event API provides programmatic access to event search functionality across multiple event providers (Eventbrite, etc.). This API is designed for developers who want to integrate event discovery into their applications.

## Base URL

```
Production: https://locomoco.lijietu.com
Development: http://localhost:8000
```

## Authentication

All API requests require an API key passed in the `X-API-Key` header.

### Getting an API Key

Contact the administrator to obtain an API key. Keys are managed using the CLI tool:

```bash
# Create a new API key
python backend/manage_api_keys.py create "My Application" --rate-limit 100

# Revoke an API key
python backend/manage_api_keys.py revoke loco_xxxxxxxxxxxxx
```

### Using Your API Key

Include the API key in the `X-API-Key` header for all requests:

```bash
curl -H "X-API-Key: loco_xxxxxxxxxxxxx" \
     https://locomoco.lijietu.com/api/v1/events/search
```

## Rate Limiting

- **Default Limit**: 100 requests per hour per API key
- **Custom Limits**: Available upon request
- **Rate Limit Headers**: All responses include:
  - `X-RateLimit-Limit`: Total requests allowed per hour
  - `X-RateLimit-Remaining`: Remaining requests in current hour
  - `Retry-After`: Seconds until rate limit resets (only on 429 errors)

### Rate Limit Error Response

```json
{
  "detail": "Rate limit exceeded. Limit: 100 requests/hour. Try again in the next hour."
}
```

**Status Code**: `429 Too Many Requests`

## API Endpoints

### 1. Search Events by City

Search for events in a specific city.

**Endpoint**: `POST /api/v1/events/search`

**Request Body**:

```json
{
  "city": "San Francisco",
  "max_pages": 3,
  "max_results": 50,
  "providers": ["eventbrite"]
}
```

**Parameters**:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `city` | string | Yes | - | City name (e.g., "San Francisco", "New York") |
| `max_pages` | integer | No | 3 | Maximum pages to fetch (1-10) |
| `max_results` | integer | No | null | Maximum number of results (1-100) |
| `providers` | array | No | all | Specific providers to use (e.g., ["eventbrite"]) |

**Supported Cities**:
- San Francisco
- New York
- Los Angeles
- Miami
- Chicago
- Seattle
- Boston

**Response**:

```json
{
  "success": true,
  "city": "San Francisco",
  "total_events": 42,
  "events": [
    {
      "title": "Jazz Night at Blue Note",
      "description": "An evening of smooth jazz...",
      "date": "2025-11-20",
      "time": "7:00 PM",
      "location": "Blue Note Jazz Club",
      "address": "131 W 3rd St, New York, NY 10012",
      "price": "$35",
      "url": "https://www.eventbrite.com/e/...",
      "image_url": "https://img.evbuc.com/...",
      "category": "Music"
    }
  ],
  "providers_used": ["eventbrite"]
}
```

**Example Request**:

```bash
curl -X POST "https://locomoco.lijietu.com/api/v1/events/search" \
  -H "X-API-Key: loco_xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "city": "San Francisco",
    "max_pages": 3,
    "max_results": 50
  }'
```

**Example with Python**:

```python
import requests

API_KEY = "loco_xxxxxxxxxxxxx"
BASE_URL = "https://locomoco.lijietu.com"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

payload = {
    "city": "San Francisco",
    "max_pages": 3,
    "max_results": 50
}

response = requests.post(
    f"{BASE_URL}/api/v1/events/search",
    headers=headers,
    json=payload
)

data = response.json()
print(f"Found {data['total_events']} events in {data['city']}")

for event in data['events']:
    print(f"- {event['title']} on {event['date']}")
```

**Example with JavaScript/Node.js**:

```javascript
const API_KEY = 'loco_xxxxxxxxxxxxx';
const BASE_URL = 'https://locomoco.lijietu.com';

async function searchEvents(city, maxPages = 3) {
  const response = await fetch(`${BASE_URL}/api/v1/events/search`, {
    method: 'POST',
    headers: {
      'X-API-Key': API_KEY,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      city: city,
      max_pages: maxPages,
      max_results: 50,
    }),
  });
  
  const data = await response.json();
  return data;
}

// Usage
searchEvents('San Francisco').then(data => {
  console.log(`Found ${data.total_events} events`);
  data.events.forEach(event => {
    console.log(`- ${event.title} on ${event.date}`);
  });
});
```

---

### 2. List Available Providers

Get a list of all available event providers and their supported cities.

**Endpoint**: `GET /api/v1/events/providers`

**Response**:

```json
{
  "success": true,
  "providers": [
    {
      "name": "eventbrite",
      "supported_cities": [
        "San Francisco",
        "New York",
        "Los Angeles",
        "Miami",
        "Chicago",
        "Seattle",
        "Boston"
      ]
    }
  ]
}
```

**Example Request**:

```bash
curl -H "X-API-Key: loco_xxxxxxxxxxxxx" \
     https://locomoco.lijietu.com/api/v1/events/providers
```

---

### 3. Get API Key Information

Get information about your API key including rate limits and remaining requests.

**Endpoint**: `GET /api/v1/events/key-info`

**Response**:

```json
{
  "name": "My Application",
  "rate_limit_per_hour": 100,
  "requests_remaining": 87
}
```

**Example Request**:

```bash
curl -H "X-API-Key: loco_xxxxxxxxxxxxx" \
     https://locomoco.lijietu.com/api/v1/events/key-info
```

---

## Error Responses

### 401 Unauthorized

Missing or invalid API key.

```json
{
  "detail": "Invalid or revoked API key."
}
```

### 429 Too Many Requests

Rate limit exceeded.

```json
{
  "detail": "Rate limit exceeded. Limit: 100 requests/hour. Try again in the next hour."
}
```

### 500 Internal Server Error

Server error during event search.

```json
{
  "detail": "Event search failed: Connection timeout"
}
```

---

## Interactive API Documentation

FastAPI provides interactive API documentation:

- **Swagger UI**: https://locomoco.lijietu.com/docs
- **ReDoc**: https://locomoco.lijietu.com/redoc

You can test API endpoints directly in the browser using these interfaces.

---

## Best Practices

### 1. **Cache Results**
Event data doesn't change frequently. Cache results for at least 1 hour to reduce API calls.

```python
import time

cache = {}
CACHE_TTL = 3600  # 1 hour

def get_events_cached(city):
    cache_key = f"events_{city}"
    
    if cache_key in cache:
        cached_data, timestamp = cache[cache_key]
        if time.time() - timestamp < CACHE_TTL:
            return cached_data
    
    # Fetch from API
    data = search_events(city)
    cache[cache_key] = (data, time.time())
    return data
```

### 2. **Handle Rate Limits Gracefully**

```python
import time

def search_with_retry(city, max_retries=3):
    for attempt in range(max_retries):
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 3600))
            print(f"Rate limited. Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            continue
        
        return response.json()
    
    raise Exception("Max retries exceeded")
```

### 3. **Monitor Your Usage**

Check remaining requests before making calls:

```python
def check_rate_limit():
    response = requests.get(
        f"{BASE_URL}/api/v1/events/key-info",
        headers={"X-API-Key": API_KEY}
    )
    data = response.json()
    
    if data['requests_remaining'] < 10:
        print(f"⚠️  Low on requests: {data['requests_remaining']} remaining")
```

### 4. **Use Specific Providers**

If you only need Eventbrite data, specify it to reduce response time:

```python
payload = {
    "city": "San Francisco",
    "providers": ["eventbrite"],  # Only use Eventbrite
    "max_pages": 2
}
```

---

## SDK Examples

### Python SDK Example

```python
# events_client.py
import requests
from typing import List, Dict, Any, Optional

class EventsClient:
    """Client for Local Life Assistant Event API."""
    
    def __init__(self, api_key: str, base_url: str = "https://locomoco.lijietu.com"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        }
    
    def search_events(
        self,
        city: str,
        max_pages: int = 3,
        max_results: Optional[int] = None,
        providers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Search for events in a city."""
        payload = {
            "city": city,
            "max_pages": max_pages,
        }
        
        if max_results:
            payload["max_results"] = max_results
        if providers:
            payload["providers"] = providers
        
        response = requests.post(
            f"{self.base_url}/api/v1/events/search",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    def list_providers(self) -> Dict[str, Any]:
        """List available event providers."""
        response = requests.get(
            f"{self.base_url}/api/v1/events/providers",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()
    
    def get_key_info(self) -> Dict[str, Any]:
        """Get API key information."""
        response = requests.get(
            f"{self.base_url}/api/v1/events/key-info",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

# Usage
if __name__ == "__main__":
    client = EventsClient(api_key="loco_xxxxxxxxxxxxx")
    
    # Search events
    result = client.search_events("San Francisco", max_pages=3)
    print(f"Found {result['total_events']} events")
    
    # Check rate limit
    info = client.get_key_info()
    print(f"Requests remaining: {info['requests_remaining']}")
```

---

## Support

For questions, issues, or feature requests:

- **GitHub Issues**: https://github.com/LijieTu/LocalLifeAssistant/issues
- **Email**: Contact the administrator
- **Documentation**: https://locomoco.lijietu.com/docs

---

## Changelog

### v2.1.0 (2025-11-16)
- ✨ Added external Event API with authentication
- ✨ Implemented rate limiting (100 req/hour default)
- ✨ Added OpenAPI/Swagger documentation
- ✨ Created API key management CLI tool
- 🔐 Secure API key storage with Firebase
- 📊 Rate limit tracking per API key

---

## License

This API is provided as-is for authorized users only. Unauthorized use is prohibited.

