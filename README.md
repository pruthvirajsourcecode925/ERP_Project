# AS9100D ERP Backend

This is the backend for the AS9100D manufacturing ERP system, built using FastAPI, PostgreSQL, and SQLAlchemy ORM. This project aims to provide a robust and scalable solution for managing manufacturing processes while adhering to AS9100D standards.

## Project Structure

```
as9100d-erp-backend
├── app
│   ├── api
│   │   ├── deps.py
│   │   └── v1
│   │       ├── api.py
│   │       └── endpoints
│   │           ├── auth.py
│   │           └── users.py
│   ├── core
│   │   ├── config.py
│   │   └── security.py
│   ├── db
│   │   ├── base.py
│   │   └── session.py
│   ├── models
│   │   └── user.py
│   ├── schemas
│   │   ├── token.py
│   │   └── user.py
│   ├── services
│   │   └── auth_service.py
│   └── main.py
├── alembic
│   ├── env.py
│   └── versions
├── tests
│   ├── test_auth.py
│   └── test_users.py
├── .env.example
├── alembic.ini
├── pyproject.toml
└── README.md
```

## Requirements

- Python 3.8 or higher
- PostgreSQL
- FastAPI
- SQLAlchemy
- Alembic
- Pydantic

## Setup Instructions

1. **Clone the repository:**
   ```
   git clone <repository-url>
   cd as9100d-erp-backend
   ```

2. **Create a virtual environment:**
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies:**
   ```
   pip install -r requirements.txt
   ```

4. **Set up the database:**
   - Create a PostgreSQL database and user.
   - Update the `.env` file with your database connection details.

5. **Run migrations:**
   ```
   alembic upgrade head
   ```

6. **Start the FastAPI application:**
   ```
   uvicorn app.main:app --reload
   ```

## Authentication

The application includes user authentication using JWT tokens. Users can register, log in, and manage their profiles. Ensure to follow the authentication flow as defined in the API documentation.

## Backend-first Development Workflow

We will complete backend API development and stabilization before starting frontend development.

Current priority order:
1. Finalize backend modules and API contracts.
2. Verify each module with tests and API collections.
3. Freeze backend endpoints and token/auth behavior.
4. Start frontend implementation after backend sign-off.

### Postman Auth Lifecycle Collection

Use the collection at [docs/postman/AS9100D-Auth-Lifecycle.postman_collection.json](docs/postman/AS9100D-Auth-Lifecycle.postman_collection.json) to validate:
- login
- me endpoint with bearer token
- refresh token rotation
- logout refresh-token revocation
- refresh failure after logout

### Auth Rate Limiter Backend

Rate limiting supports two backends:
- `memory` (default): suitable for local/dev and single instance
- `redis`: recommended for multi-instance production

Environment variables:
- `AUTH_RATE_LIMIT_WINDOW_SECONDS`
- `AUTH_LOGIN_MAX_REQUESTS`
- `AUTH_REFRESH_MAX_REQUESTS`
- `AUTH_RATE_LIMIT_BACKEND` (`memory` or `redis`)
- `AUTH_RATE_LIMIT_REDIS_URL` (required when backend is `redis`)

## Documentation

- Sales ER Diagram: [docs/sales-erd.md](docs/sales-erd.md)

## Sales Contract Review Gate (Backend)

Quotation creation and quotation PDF download are blocked unless all 5 contract-review checks are `True`.

Business label to backend field mapping:
- `drawing_available` -> `scope_clarity_ok`
- `special_process_identified` -> `capability_ok`
- `capacity_ok` -> `capacity_ok`
- `delivery_feasible` -> `delivery_commitment_ok`
- `quality_requirements_clear` -> `quality_requirements_ok`

If any check is `False`, the API responds with HTTP 400 and a clear message listing which checkbox names must be set to `Yes/True`.

Example 400 response:

```json
{
   "detail": "Quotation cannot be generated due to incomplete contract review.\n\nThe following feasibility items are not approved:\n• Drawing availability\n• Delivery feasibility\n\nPlease resolve the above issues before generating quotation."
}
```

## Testing

Unit tests are included for both authentication and user management. To run the tests, use:
```
pytest
```

## License

This project is licensed under the MIT License. See the LICENSE file for more details.