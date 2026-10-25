# Request correlation IDs

Every HTTP response includes `X-Request-ID`. A caller-supplied value is retained
only when it is 1-128 ASCII characters and contains letters, digits, `.`, `_`, or
`-`, beginning with a letter or digit. Missing or unsafe values are replaced by a
server-generated UUIDv4 rather than reflected into response headers or logs.

During request processing the validated value is available as
`request.state.request_id` and through `app.request_context.get_request_id()`.
Metadata-only audit events written during that request include the same
`request_id`; callers cannot override that field through audit details. The
context is reset at the end of the request so background work cannot inherit a
stale HTTP correlation ID.

Browser clients may read the header because it is included in the CORS exposed
header list. The ID is operational correlation metadata, not evidence of user
identity, data integrity, or clinical provenance.
