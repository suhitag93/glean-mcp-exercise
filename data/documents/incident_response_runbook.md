# Incident Response Runbook

**Document ID:** eng-incident-runbook-v2  
**Category:** Engineering / Operations  
**Last Updated:** 2025-01-28  
**Owner:** Site Reliability Engineering (SRE)

## Severity Levels

| Severity | Definition | Response Time | Example |
|---|---|---|---|
| **SEV-1** | Complete outage or data loss | 15 minutes | API down for all users |
| **SEV-2** | Major feature unavailable | 30 minutes | Checkout broken for 20%+ of users |
| **SEV-3** | Degraded performance | 2 hours | Elevated latency, no user impact |
| **SEV-4** | Minor issue | Next business day | Cosmetic bug |

## On-Call Rotation

The on-call schedule is managed in **PagerDuty**. Each engineering team has a primary and secondary on-call engineer on a weekly rotation.

- Primary: First responder for all SEV-1 and SEV-2 alerts
- Secondary: Backup if primary is unreachable (after 5-minute escalation)

Engineers can view the current on-call schedule at https://pagerduty.acme-corp.example.com or via the `/oncall` Slack command in any channel.

## SEV-1 Response Steps

### 1. Acknowledge (within 15 min of alert)

- Acknowledge the PagerDuty alert to stop escalation
- Post in **#incidents** Slack channel: "Acknowledging SEV-1 – [brief description]. IC: @your-name"
- You are now the **Incident Commander (IC)**

### 2. Assess and Declare

- Check dashboards: Datadog APM, CloudWatch, and the Status Page
- If confirmed outage: Run `/incident declare sev1` in Slack to auto-create an incident channel and page the on-call SRE lead

### 3. Investigate

Common first steps:
```bash
# Check recent deployments
kubectl rollout history deployment/api-server -n production

# Check pod health
kubectl get pods -n production | grep -v Running

# Tail logs
kubectl logs -n production -l app=api-server --tail=100 -f

# Check error rates in Datadog
# Navigate to: APM > Services > api-server > Errors
```

### 4. Mitigate

If caused by a recent deployment:
```bash
# Rollback the deployment
kubectl rollout undo deployment/api-server -n production

# Verify rollback
kubectl rollout status deployment/api-server -n production
```

If caused by a database issue, page the DBA on-call via PagerDuty policy `database-oncall`.

### 5. Communicate

- Update the **Status Page** at https://status.acme-corp.example.com every 15 minutes during an active SEV-1
- Notify #customer-success so they can communicate with affected customers
- Send an update to leadership via the #exec-updates Slack channel

### 6. Resolve and Post-Mortem

- Mark the incident resolved in PagerDuty when service is restored
- Schedule a blameless post-mortem within **48 hours** using the Post-Mortem template in Confluence
- Post-mortems for SEV-1 incidents are mandatory

## Useful Dashboards

- **API Health**: https://datadog.acme-corp.example.com/dashboard/api-health
- **Infrastructure**: https://datadog.acme-corp.example.com/dashboard/infra
- **Database**: https://datadog.acme-corp.example.com/dashboard/rds

## Contact the SRE Team

- Slack: #sre-help (non-urgent) or #incidents (active incidents)
- PagerDuty: Policy `sre-escalation` for any SEV-1 not acknowledged within 5 minutes
