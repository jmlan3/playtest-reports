# HTTP API rather than REST API: cheaper and simpler, and this project needs
# none of REST's extras (API keys, usage plans, request validation).
resource "aws_apigatewayv2_api" "http" {
  name          = var.project
  protocol_type = "HTTP"
}

# Hands each request to the Lambda as a payload format 2.0 event, which is
# what the handler expects (routeKey, lowercase header names).
resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.api.invoke_arn
  payload_format_version = "2.0"
}

# Any other method or path gets a 404 from API Gateway without invoking the
# Lambda.
resource "aws_apigatewayv2_route" "reports" {
  for_each = toset(["POST /reports", "GET /reports"])

  api_id    = aws_apigatewayv2_api.http.id
  route_key = each.key
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

# $default is served at the API's root URL with no stage name in the path.
# auto_deploy publishes route changes without a separate deployment step.
resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true

  # Stage-wide throttling. Requests over the limit get a 429 from API Gateway
  # and never reach (or bill) the Lambda.
  default_route_settings {
    throttling_rate_limit  = var.throttle_rate_limit
    throttling_burst_limit = var.throttle_burst_limit
  }
}

# Lets this API, and only this API's /reports routes, invoke the function.
resource "aws_lambda_permission" "api" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*/reports"
}
