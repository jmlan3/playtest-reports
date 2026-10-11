# Bucket names are global across all AWS accounts. The usual trick of adding
# the account ID would publish it in this public repo, so use random hex.
resource "random_id" "state_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "state" {
  bucket = "${var.project}-tfstate-${random_id.state_suffix.hex}"

  # Losing this bucket means Terraform loses track of everything in infra/.
  # Terraform refuses any plan that would delete it.
  lifecycle {
    prevent_destroy = true
  }
}

# Every state write keeps the previous version, so a bad apply or a
# corrupted state file can be rolled back.
resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id

  versioning_configuration {
    status = "Enabled"
  }
}

# Old versions are only needed for a while; this stops them piling up forever.
resource "aws_s3_bucket_lifecycle_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    id     = "expire-old-state-versions"
    status = "Enabled"
    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }

  depends_on = [aws_s3_bucket_versioning.state]
}

# SSE-S3: AES-256 with keys managed by S3, at no extra cost. SSE-KMS would add
# key-level access control and audit logs, but also per-request KMS charges
# and a key policy to manage; access to this bucket is already limited by IAM.
resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# New buckets already block public access by default; stating it here keeps
# it that way even if someone changes it in the console (the next plan shows
# the drift).
resource "aws_s3_bucket_public_access_block" "state" {
  bucket = aws_s3_bucket.state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Refuse any request that isn't over HTTPS.
data "aws_iam_policy_document" "state_bucket" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.state.arn, "${aws_s3_bucket.state.arn}/*"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "state" {
  bucket = aws_s3_bucket.state.id
  policy = data.aws_iam_policy_document.state_bucket.json

  # Applying a bucket policy while the public access block is still being
  # created can fail, so wait for it.
  depends_on = [aws_s3_bucket_public_access_block.state]
}
