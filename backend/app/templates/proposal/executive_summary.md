# Executive Summary

**Project ID:** {{project_id}}  
**Project Name:** {{project_name}}  
**Project Address:** {{project_address}}  
**Date:** {{generated_date}}

## Total Bid Amount

**{{total_bid_formatted}}**

{{#if subtotals}}
### Cost Breakdown

{{#each subtotals}}
- **{{@key}}:** {{this_formatted}}
{{/each}}
{{/if}}

{{#if estimated_duration}}
**Estimated Duration:** {{estimated_duration}} weeks
{{/if}}

{{#if region_resolution}}
**Region:** {{region_resolution.region_id}} (confidence: {{region_resolution.confidence_percent}}%)
{{/if}}






