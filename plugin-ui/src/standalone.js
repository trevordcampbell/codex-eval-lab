import { mountReview } from './review.js';
// Explicit offline mode: no MCP bridge initialization and no network calls.
mountReview(JSON.parse(document.getElementById('review-data').textContent));
