# 🚀 Event API Quick Start Guide

Get started with the Local Life Assistant Event API in 5 minutes!

## Step 1: Get an API Key

Contact the administrator or use the CLI tool to create an API key:

```bash
cd backend
python manage_api_keys.py create "My App"
```

**Output**:
```
============================================================
✅ API Key Created Successfully!
============================================================

API Key: loco_xxxxxxxxxxxxx

⚠️  IMPORTANT: Save this key now! It won't be shown again.
============================================================
```

**Save this key securely!** You'll need it for all API requests.

## Step 2: Test Your API Key

```bash
curl -H "X-API-Key: loco_xxxxxxxxxxxxx" \
     https://locomoco.lijietu.com/api/v1/events/key-info
```

**Expected Response**:
```json
{
  "name": "My App",
  "rate_limit_per_hour": 100,
  "requests_remaining": 100
}
```

## Step 3: Search for Events

```bash
curl -X POST "https://locomoco.lijietu.com/api/v1/events/search" \
  -H "X-API-Key: loco_xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "city": "San Francisco",
    "max_pages": 3,
    "max_results": 20
  }'
```

**Response**:
```json
{
  "success": true,
  "city": "San Francisco",
  "total_events": 18,
  "events": [
    {
      "title": "Tech Meetup: AI & Machine Learning",
      "date": "2025-11-20",
      "time": "6:00 PM",
      "location": "TechHub SF",
      "price": "Free",
      "url": "https://www.eventbrite.com/e/..."
    }
  ],
  "providers_used": ["eventbrite"]
}
```

## Step 4: Integrate into Your App

### Python Example

```python
import requests

API_KEY = "loco_xxxxxxxxxxxxx"
BASE_URL = "https://locomoco.lijietu.com"

def search_events(city):
    response = requests.post(
        f"{BASE_URL}/api/v1/events/search",
        headers={
            "X-API-Key": API_KEY,
            "Content-Type": "application/json"
        },
        json={"city": city, "max_pages": 3}
    )
    return response.json()

# Use it
events = search_events("San Francisco")
print(f"Found {events['total_events']} events!")
```

### JavaScript Example

```javascript
const API_KEY = 'loco_xxxxxxxxxxxxx';
const BASE_URL = 'https://locomoco.lijietu.com';

async function searchEvents(city) {
  const response = await fetch(`${BASE_URL}/api/v1/events/search`, {
    method: 'POST',
    headers: {
      'X-API-Key': API_KEY,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ city, max_pages: 3 }),
  });
  return await response.json();
}

// Use it
searchEvents('San Francisco').then(data => {
  console.log(`Found ${data.total_events} events!`);
});
```

## Step 5: Explore Interactive Docs

Visit the interactive API documentation:

- **Swagger UI**: https://locomoco.lijietu.com/docs
- **ReDoc**: https://locomoco.lijietu.com/redoc

You can test all endpoints directly in your browser!

---

## Supported Cities

- San Francisco
- New York
- Los Angeles
- Miami
- Chicago
- Seattle
- Boston

---

## Rate Limits

- **Default**: 100 requests/hour
- **Headers**: Check `X-RateLimit-Remaining` in responses
- **Need more?** Contact admin for custom limits

---

## Common Issues

### 401 Unauthorized
❌ **Problem**: Invalid API key  
✅ **Solution**: Check that your API key is correct and not revoked

### 429 Too Many Requests
❌ **Problem**: Rate limit exceeded  
✅ **Solution**: Wait for the next hour or request a higher limit

### 500 Internal Server Error
❌ **Problem**: Server error  
✅ **Solution**: Check if the city name is supported, try again later

---

## Next Steps

- 📖 Read the [Full API Documentation](./API_DOCUMENTATION.md)
- 🧪 Run the test suite: `pytest backend/tests/test_api_*.py`
- 🔧 Customize rate limits: `python manage_api_keys.py create "App" --rate-limit 500`
- 🚀 Deploy your integration!

---

## Need Help?

- **Documentation**: https://locomoco.lijietu.com/docs
- **GitHub Issues**: https://github.com/LijieTu/LocalLifeAssistant/issues
- **Email**: Contact administrator

---

**Happy coding! 🎉**

