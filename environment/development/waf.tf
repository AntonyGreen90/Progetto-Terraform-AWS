# Web ACL per CloudFront
resource "aws_wafv2_web_acl" "cloudfront" {
  provider    = aws.virginia
  name        = "project-cloudfront-waf"
  description = "WAF for the project CloudFront distribution"
  scope       = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "AWSCommonRules"
    priority = 1

    # Modalità di osservazione: non blocca
    override_action {
      count {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSCommonRules"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "project-cloudfront-waf"
    sampled_requests_enabled   = true
  }

  tags = {
    Project     = "DevOpsTraining"
    Environment = "Training"
  }
}