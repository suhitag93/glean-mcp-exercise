# Acme Platform API – Rate Limits and Quotas

**Document ID:** eng-api-rate-limits-v3  
**Category:** Engineering / Platform  
**Last Updated:** 2025-02-20  
**Owner:** Platform Engineering

## Overview

The Acme Platform API enforces per-tenant rate limits to ensure fair usage and protect service stability. All limits apply per **API key** unless otherwise noted.

## Default Rate Limits

| Endpoint Group | Requests per Second | Requests per Minute | Requests per Day |
|---|---|---|---|
| `/v1/search` | 10 | 300 | 50,000 |
| `/v1/documents` (read) | 50 | 1,000 | 500,000 |
| `/v1/documents` (write) | 5 | 100 | 10,000 |
| `/v1/users` | 10 | 300 | 50,000 |
| `/v1/webhooks` | 2 | 30 | 5,000 |
| All other endpoints | 20 | 500 | 100,000 |

## Enterprise Tier Limits

Enterprise customers have 10x the default limits above. Custom limits can be negotiated by contacting your account manager.

## Rate Limit Headers

Every API response includes the following headers:

```
X-RateLimit-Limit: 300          # Requests allowed in the current window
X-RateLimit-Remaining: 247      # Requests remaining in the current window
X-RateLimit-Reset: 1706745600   # Unix timestamp when the window resets
X-RateLimit-Window: 60          # Window duration in seconds
```

## Handling Rate Limit Errors

When a rate limit is exceeded, the API returns:

```
HTTP 429 Too Many Requests
Retry-After: 14    # seconds until the limit resets
```

### Recommended Retry Strategy

Use exponential backoff with jitter when handling 429 responses:

```python
import time
import random

def api_call_with_retry(func, max_retries=5):
    for attempt in range(max_retries):
        response = func()
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 2 ** attempt))
            jitter = random.uniform(0, 1)
            time.sleep(retry_after + jitter)
            continue
        return response
    raise Exception("Max retries exceeded")
```

## Burst Allowance

Each API key is granted a **burst allowance** of 2x the per-second rate limit for up to 5 consecutive seconds before throttling begins. This accommodates short bursts from batch operations.

## Quota Increases

To request a rate limit increase:

1. Open a ticket in the **Developer Portal** at https://developers.acme-corp.example.com
2. Select "Rate Limit Increase Request"
3. Provide: current usage metrics, justification, and target limits
4. Allow 3–5 business days for review

## IP-Based Limits

In addition to key-based limits, the API enforces a global limit of **1,000 requests per minute per IP address** to prevent abuse. Legitimate high-volume clients should distribute requests across multiple IPs or contact support.

## Webhook Delivery Limits

Webhooks are retried up to **5 times** with exponential backoff (1s, 2s, 4s, 8s, 16s) on delivery failure. After 5 failures, the webhook is marked as failed and the endpoint is temporarily suspended for 1 hour.

## Contact

Platform Engineering: #platform-help on Slack or platform-eng@acme-corp.example.com
