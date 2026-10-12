output "reports_url" {
  description = "Where the game POSTs reports and where you GET them by build."
  value       = "${aws_apigatewayv2_stage.default.invoke_url}reports"
}

output "table_name" {
  value = aws_dynamodb_table.reports.name
}

output "function_name" {
  value = aws_lambda_function.api.function_name
}

output "log_group_name" {
  value = aws_cloudwatch_log_group.lambda.name
}
