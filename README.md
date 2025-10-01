# Generac AWS Notifier

Monitor your Generac generators and propane tank monitors with AWS EventBridge, Lambda, and receive notifications via SNS or SES when status changes occur.

This project is adapted from the [ha-generac](https://github.com/binarydev/ha-generac) Home Assistant integration, repurposed as a standalone AWS service focused on status monitoring and notifications.

## Features

- 🔄 **Automated Monitoring**: Periodic checks of generator status via AWS EventBridge
- 📊 **State Tracking**: Stores previous state in DynamoDB to detect changes
- 📧 **Flexible Notifications**: Send alerts via SNS or SES (email)
- 🔋 **Comprehensive Alerts**:
  - Generator status changes (Ready, Running, Exercising, etc.)
  - Connectivity changes
  - Maintenance alerts
  - Warning conditions
  - Low battery voltage
- ⚙️ **Configurable**: Customize check frequency and notification preferences
- 🏗️ **Infrastructure as Code**: Deploy with AWS SAM

## Architecture

```
EventBridge Schedule (every 5 min)
           ↓
    Lambda Function
           ↓
    Generac API (MobileLink)
           ↓
    DynamoDB (state storage)
           ↓
    SNS/SES (notifications)
```

## Prerequisites

1. **Generac MobileLink Account**: Active account at https://app.mobilelinkgen.com/
2. **AWS Account**: With permissions to create Lambda, DynamoDB, EventBridge, SNS, and SES resources
3. **AWS SAM CLI**: [Install AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
4. **Python 3.11+**: For local development/testing

## Getting the Session Cookie

The Generac API requires authentication via a session cookie (username/password login is blocked by CAPTCHA):

1. Log into https://app.mobilelinkgen.com/ and navigate to one of your devices
2. Open browser Developer Tools (right-click → Inspect)
3. Go to the **Network** tab and refresh the page
4. Click the first request in the list (should match your device ID in the URL)
5. In the **Headers** tab, scroll down to find the **Cookie** field
6. Copy the entire cookie value (it will be very long, thousands of characters)

⚠️ **Important**: Keep this cookie secure. Store it in AWS Secrets Manager or parameter store for production use.

## Deployment

### 1. Clone the Repository

```bash
git clone https://github.com/landonix/generac-aws-notifier.git
cd generac-aws-notifier
```

### 2. Store Session Cookie in AWS Secrets Manager

Store your session cookie securely in AWS Secrets Manager:

```bash
aws secretsmanager create-secret \
  --name generac-notifier/session-cookie \
  --secret-string "YOUR_VERY_LONG_SESSION_COOKIE_HERE" \
  --region us-east-1
```

⚠️ **Important**: Replace `YOUR_VERY_LONG_SESSION_COOKIE_HERE` with the actual cookie you copied from step 1.

### 3. Deploy with SAM

```bash
# Build the application
sam build

# Deploy with your email configuration
sam deploy \
  --guided \
  --parameter-overrides \
    SesToEmails="your-email@example.com" \
    SesFromEmail="your-email@example.com"
```

On first deployment, SAM will ask you questions:
- Stack name: `generac-notifier` (or choose your own)
- AWS Region: `us-east-1` (or your preferred region)
- Confirm changes: `Y`
- Allow SAM CLI IAM role creation: `Y`
- Save arguments to configuration: `Y`

After the first deployment, you can simply run:
```bash
sam build && sam deploy
```

### 4. Verify Email Addresses (for SES)

If using SES in sandbox mode, you must verify recipient email addresses:

```bash
aws ses verify-email-identity --email-address your-email@example.com
```

Check your inbox for a verification email from AWS.

## Configuration Options

### Deployment Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `GeneracSessionCookie` | ✅ Yes | - | Session cookie from Generac MobileLink |
| `CheckSchedule` | No | `rate(5 minutes)` | EventBridge schedule expression |
| `SnsTopicArn` | No | - | SNS topic ARN for notifications |
| `SesFromEmail` | No | - | From email address for SES |
| `SesToEmails` | No | - | Comma-separated recipient emails |
| `NotifyOnStatusChange` | No | `true` | Enable status change notifications |
| `NotifyOnConnectivityChange` | No | `true` | Enable connectivity notifications |
| `NotifyOnMaintenanceAlert` | No | `true` | Enable maintenance alert notifications |
| `NotifyOnWarning` | No | `true` | Enable warning notifications |
| `NotifyOnLowBattery` | No | `true` | Enable low battery notifications |
| `LowBatteryThreshold` | No | `12.0` | Battery voltage threshold (volts) |

### Schedule Expressions

Use rate or cron expressions for `CheckSchedule`:

- `rate(5 minutes)` - Every 5 minutes
- `rate(1 hour)` - Every hour
- `cron(0 */6 * * ? *)` - Every 6 hours
- `cron(0 8 * * ? *)` - Daily at 8 AM UTC

## Monitoring

### CloudWatch Logs

View Lambda execution logs:

```bash
sam logs -n GeneracMonitorFunction --tail
```

Or in the AWS Console:
1. Go to CloudWatch → Log groups
2. Find `/aws/lambda/generac-notifier-monitor`

### Manual Invocation

Test the Lambda function manually:

```bash
aws lambda invoke \
  --function-name generac-notifier-monitor \
  --payload '{}' \
  response.json

cat response.json
```

### DynamoDB State

View stored device states:

```bash
aws dynamodb scan --table-name generac-notifier-device-state
```

## Notification Examples

### Status Change

```
Subject: Generator Alert: Home Generator

Your Generator has reported status changes.

Device: Home Generator
Serial Number: ABC123456

Changes:
  • Status changed: Ready → Running

Current Status:
Status: Running
Connected: Yes
Battery: 13.2V

Timestamp: 2025-10-01T15:30:00Z
```

### Low Battery

```
Subject: Generator Alert: Home Generator

Your Generator has reported status changes.

Device: Home Generator
Serial Number: ABC123456

Changes:
  • Battery voltage: 13.1V → 11.8V

Current Status:
Status: Ready
Connected: Yes
Battery: 11.8V
🔋 Low Battery Warning

Timestamp: 2025-10-01T15:35:00Z
```

## Cost Estimates

Approximate AWS costs (us-east-1, as of 2025):

| Service | Usage | Monthly Cost |
|---------|-------|--------------|
| Lambda | 8,640 invocations (5 min intervals) | < $0.01 |
| DynamoDB | On-demand, minimal storage | < $0.25 |
| EventBridge | 8,640 events | Free tier |
| SNS | 1,000 notifications | < $0.50 |
| SES | 1,000 emails | $0.10 |
| **Total** | | **< $1.00/month** |

## Troubleshooting

### Session Cookie Expired

If you receive `SessionExpiredException` errors:
1. Get a new session cookie from Generac MobileLink
2. Update the secret in AWS Secrets Manager:
   ```bash
   aws secretsmanager update-secret \
     --secret-id generac-notifier/session-cookie \
     --secret-string "NEW_COOKIE" \
     --region us-east-1
   ```

   The Lambda function will automatically use the new cookie on its next run.

### No Notifications Received

1. Check Lambda logs for errors
2. Verify notification settings in parameters
3. For SES: Ensure email addresses are verified
4. For SNS: Check topic subscription confirmation

### Lambda Timeout

If checks timeout with many devices:
1. Increase Lambda timeout in `template.yaml` (Globals → Function → Timeout)
2. Redeploy: `sam build && sam deploy`

## Development

### Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GENERAC_SESSION_COOKIE="your_cookie"
export DYNAMODB_TABLE="test-table"

# Run tests
pytest tests/
```

### Project Structure

```
generac-aws-notifier/
├── src/
│   ├── __init__.py
│   ├── lambda_handler.py      # Main Lambda entry point
│   ├── generac_api.py          # Generac API client
│   ├── models.py               # Data models
│   ├── config.py               # Configuration
│   ├── state_manager.py        # DynamoDB state management
│   └── notifier.py             # Notification logic
├── tests/                      # Unit tests
├── template.yaml               # SAM template
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## Cleanup

Remove all AWS resources:

```bash
sam delete
```

This will delete:
- Lambda function
- DynamoDB table (data will be lost!)
- EventBridge rule
- CloudWatch log group
- IAM roles

## Credits

This project is adapted from the [ha-generac](https://github.com/binarydev/ha-generac) Home Assistant integration by [@binarydev](https://github.com/binarydev), which was originally forked from [@bentekkie](https://github.com/bentekkie/ha-generac).

Special thanks to the contributors of the original project for reverse-engineering the Generac MobileLink API.

## License

MIT License - See LICENSE file for details

## Disclaimer

This is an unofficial project and is not affiliated with, endorsed by, or connected to Generac Power Systems, Inc. Use at your own risk. The Generac MobileLink API is not publicly documented and may change without notice.
