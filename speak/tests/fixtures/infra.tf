resource "aws_db_instance" "pagos" {
  engine = "aurora-postgresql"
  multi_az = true
}
