# Email Configuration

The backend exposes a pluggable email provider abstraction so outbound messages
can be routed through the service that best fits the deployment environment. At
startup the application reads configuration from environment variables and
instantiates the appropriate provider. Unknown provider names fall back to the
basic SMTP implementation.

## Environment variables

| Variable | Description | Default |
| --- | --- | --- |
| `EMAIL_PROVIDER` | Provider to use. Supported values: `smtp`, `sendgrid`, `ses`. Unknown values log a warning and fall back to SMTP. | `smtp` |
| `EMAIL_SENDER` | Display name/address used as the logical sender in emails. | `noreply@example.com` |
| `EMAIL_RATE_LIMIT_PER_MINUTE` | Optional soft rate limit included in logs for observability. | _unset_ |
| `EMAIL_SMTP_HOST` | Hostname of the SMTP relay. | `localhost` |
| `EMAIL_SMTP_PORT` | TCP port of the SMTP relay. | `25` |
| `EMAIL_SMTP_USERNAME` | Optional username for SMTP authentication. | _unset_ |
| `EMAIL_SMTP_PASSWORD` | Optional password for SMTP authentication. | _unset_ |
| `EMAIL_SMTP_USE_TLS` | Whether to negotiate TLS when using SMTP. Accepts `1/0`, `true/false`, `yes/no`. | `true` |
| `SENDGRID_API_KEY` | API key used when `EMAIL_PROVIDER=sendgrid`. Required for SendGrid. | _unset_ |
| `SES_ACCESS_KEY_ID` | AWS access key for SES. If unset, `AWS_ACCESS_KEY_ID` is used. Required for SES. | _unset_ |
| `SES_SECRET_ACCESS_KEY` | AWS secret key for SES. If unset, `AWS_SECRET_ACCESS_KEY` is used. Required for SES. | _unset_ |
| `SES_REGION` | AWS region hosting SES. If unset, `AWS_REGION` is used. Required for SES. | _unset_ |

## Provider specifics

### SMTP

The default provider relays messages over SMTP using the connection parameters
above. If credentials are omitted the connection will attempt to authenticate
anonymously.

### SendGrid

When `EMAIL_PROVIDER=sendgrid` the `SENDGRID_API_KEY` variable must be provided.
No network calls are made in the development stubs, but the key is validated so
that misconfiguration is surfaced early.

### Amazon SES

When `EMAIL_PROVIDER=ses` the application expects credentials via the SES- or
AWS-prefixed environment variables and a region. Missing any of these values
results in startup failure.

## Fallback behaviour

If an unsupported provider name is configured the application logs a warning
and instantiates the SMTP provider using the configured SMTP parameters. This
prevents deployments from silently dropping emails due to typos while retaining
sensible defaults for local development.