# Working with Gear Bot gears

A "gear bot" gear is a gear that uses the API token of the Gear Bot user in Flywheel.

This user has a UW shared net ID nacc-flywheel-gear, and an AWS IAM user nacc-flywheel-gear.

The Flywheel instances are configured to provide the AWS credentials for this user through environment variables, which allows the gear to access the AWS SSM parameter store to access the gearbot API key.

A gear bot may also use other AWS services as determined by the policy settings for the IAM user.

## AWS IAM policies

The Gear Bot has the AWS IAM user nacc-flywheel-gear.

For each service that the gear bot uses, policies need to be set in IAM.
There are existing policies for accessing SSM parameters, and for running the identifiers lambdas.

Access to parameters used by a gear are set by the  `nacc-flywheel-gear-bot-parameter-access` policy.
To reach the policy, open the nacc-flywheel-gear user in IAM on the AWS console, and the policies are listed under permissions.
Click the policy name and then click the Edit button to access the policy.

The policy is written so that allows are specific, and denys are general.
So, you should only need to add parameters or new paths to the allows.
