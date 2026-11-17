param([Parameter(ValueFromRemainingArguments=$true)]$Args)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $here
python -m blacky.main @Args
