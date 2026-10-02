#Requires -Version 5.1
# SPDX-FileCopyrightText: 2026 Nicholas Warila
# SPDX-License-Identifier: MIT

<#
    .SYNOPSIS
        Moves kept data disks to their declared drive letters.

    .DESCRIPTION
        Resolves each declared disk and its largest data partition, then checks every move before
        changing anything. A target held outside the kept set is refused without removing any
        current letter. Rotations within the kept set are allowed: every old letter is removed
        before any target is assigned.

        Each assignment is read back. A write that does not take fails the run instead of
        reporting a successful move. Check mode and standalone -WhatIf report the pending moves
        without writing. In the result, after starts as before. It becomes empty only after a
        guarded removal returns, and becomes the target only after a guarded assignment returns.
        A skipped or throwing call does not advance it.

        Org scripts are a single straightforward process stage in the org script template's
        architecture: one [ Script ] region carrying [ Initialization ], [ Main ] and [ Output ].
        The script is developed under scripts/ with its sibling Pester spec and is materialized
        into the role from files/Set-DiskDriveLetter.ps1.stub.

    .PARAMETER DebugLevel
        Three-digit control string configuring ErrorActionPreference, Set-PSDebug and
        Set-StrictMode. Default '103': stop on error, no tracing, strict mode 3.

    .PARAMETER DriveLetter
        The declared one-letter targets, paired by position with UniqueId.

    .PARAMETER LogLevel
        Six-digit control string setting Verbose, Debug, Information, Warning, Error and Fatal.

    .PARAMETER UniqueId
        The unique disk identifiers, paired by position with DriveLetter.

    .OUTPUTS
        System.String -- standalone, the result object as JSON: changed, check_mode, disks,
        held_by and msg. Under the transport it is $Ansible.Result.
#>

[CmdletBinding(
  ConfirmImpact = 'None',
  DefaultParameterSetName = 'default',
  HelpUri = '',
  PositionalBinding = $False,
  RemotingCapability = 'PowerShell',
  SupportsPaging = $False,
  SupportsShouldProcess = $True
)]
[OutputType([System.String])]
Param (
  [Parameter(
    DontShow = $False,
    Mandatory = $False,
    ParameterSetName = 'default',
    ValueFromPipeline = $False,
    ValueFromPipelineByPropertyName = $False
  )]
  [ValidatePattern('^[0-5][0-4][0-3]$')]
  [System.String]
  $DebugLevel = '103',

  [Parameter(
    DontShow = $False,
    Mandatory = $True,
    ParameterSetName = 'default',
    ValueFromPipeline = $False,
    ValueFromPipelineByPropertyName = $False
  )]
  [AllowEmptyCollection()]
  [AllowEmptyString()]
  [System.String[]]
  $DriveLetter,

  [Parameter(
    DontShow = $False,
    Mandatory = $False,
    ParameterSetName = 'default',
    ValueFromPipeline = $False,
    ValueFromPipelineByPropertyName = $False
  )]
  [ValidatePattern('^[0-5]{6}$')]
  [System.String]
  $LogLevel = '002223',

  [Parameter(
    DontShow = $False,
    Mandatory = $True,
    ParameterSetName = 'default',
    ValueFromPipeline = $False,
    ValueFromPipelineByPropertyName = $False
  )]
  [AllowEmptyCollection()]
  [AllowEmptyString()]
  [System.String[]]
  $UniqueId
)

#region ------ [ Script ] -------------------------------------------------------------------- #

#region ------ [ Initialization ] ------------------------------------------------------------ #
Write-Debug -Message:'Entering Stage: Initialization'

# The module injects -WhatIf in check mode. Remember a standalone request before neutralising
# the preference for setup; ShouldProcess still observes the invocation's -WhatIf request.
$WhatIfRequested = [System.Boolean]$WhatIfPreference
$WhatIfPreference = $False

New-Variable -Force -Name:'LOG_LEVELS' -Option:('Private', 'ReadOnly') -Value:(
  [System.String[]]@('Verbose', 'Debug', 'Information', 'Warning', 'Error', 'Fatal')
)
New-Variable -Verbose:$False -Force -Name:'ErrorPreference' -Value:(
  [System.Management.Automation.ActionPreference]::Stop
)
New-Variable -Verbose:$False -Force -Name:'FatalPreference' -Value:(
  [System.Management.Automation.ActionPreference]::Stop
)

For ($L = 0; $L -lt 6; $L++) {
  Set-Variable -Verbose:$False -Force -Name:('{0}Preference' -f $LOG_LEVELS[$L]) -Value:(
    [System.Int32]::Parse([System.String]$LogLevel[$L]) -as
    [System.Management.Automation.ActionPreference]
  )
}

$ErrorActionPreference = [System.Management.Automation.ActionPreference][System.Int32]::Parse(
  $DebugLevel.Substring(0, 1)
)
Switch ($DebugLevel.Substring(1, 1)) {
  '0' { Set-PSDebug -Off }
  '1' { Set-PSDebug -Trace:1 }
  '2' { Set-PSDebug -Trace:2 }
  '3' { Set-PSDebug -Trace:1 -Step }
  '4' { Set-PSDebug -Trace:2 -Step }
}
If ($DebugLevel.Substring(2, 1) -eq '0') {
  Set-StrictMode -Off
} Else {
  Set-StrictMode -Version:([System.String]$DebugLevel.Substring(2, 1))
}

Trap {
  Try {
    If ($PSItem.Exception.PSObject.Properties.Name -contains 'ErrorRecord') {
      Write-Debug -Message:(
        'Failed to execute command: {0}' -f
        [System.String]$PSItem.Exception.ErrorRecord.InvocationInfo.Line
      )
    }
    Write-Warning -Message:(
      '[{0:0000}] {1} [{2}]' -f @(
        [System.Int64]$PSItem.InvocationInfo.ScriptLineNumber
        [System.String]$PSItem.Exception.Message
        [System.String]$PSItem.Exception.GetBaseException().GetType().FullName
      )
    )
  } Catch {
    Write-Debug -Message:'Trap diagnostics unavailable for this error record.'
  }

  Break
}

$StandaloneRun = $Null -eq (
  Get-Variable -Name:'Ansible' -ValueOnly -ErrorAction:'SilentlyContinue'
)
If ($StandaloneRun) {
  $Ansible = [PSCustomObject]@{
    Changed   = $True
    CheckMode = $WhatIfRequested
    Failed    = $False
    Result    = $Null
  }
}

#endregion --- [ Initialization ] ------------------------------------------------------------ #

#region ------ [ Main ] ---------------------------------------------------------------------- #
Write-Debug -Message:'Entering Stage: Main'

# These values exist before the guarded body so every post-binding failure can publish the same
# contract. No change is the default, including input, discovery and holder failures.
$Ansible.Changed = $False
$Disks = @()
$HeldBy = $Null

Try {
  If ($UniqueId.Count -ne $DriveLetter.Count) {
    Throw (
      'UniqueId has {0} entries and DriveLetter has {1}; they pair one to one.' -f
      $UniqueId.Count, $DriveLetter.Count
    )
  }
  If ($UniqueId.Count -lt 1) {
    Throw 'UniqueId and DriveLetter must contain at least one entry.'
  }

  # Validate the complete declaration before the first platform read.
  $Targets = @()
  $SeenIds = @{}
  $SeenLetters = @{}
  For ($I = 0; $I -lt $UniqueId.Count; $I++) {
    If ([System.String]::IsNullOrEmpty($UniqueId[$I])) {
      Throw ('UniqueId entry {0} is empty.' -f $I)
    }
    If ($SeenIds.ContainsKey($UniqueId[$I])) {
      Throw ('UniqueId ''{0}'' is repeated.' -f $UniqueId[$I])
    }
    $SeenIds[$UniqueId[$I]] = $True

    If ($DriveLetter[$I] -notmatch '^[A-Za-z]$') {
      Throw ('DriveLetter ''{0}'' is not one letter.' -f $DriveLetter[$I])
    }
    $Target = $DriveLetter[$I].ToUpperInvariant()
    If ($SeenLetters.ContainsKey($Target)) {
      Throw ('DriveLetter ''{0}'' is repeated.' -f $Target)
    }
    $SeenLetters[$Target] = $True
    $Targets += $Target
  }

  # Keep internal target data separate from the exact six-key public disk maps.
  $Resolved = @()
  For ($I = 0; $I -lt $UniqueId.Count; $I++) {
    $DiskMatches = @(
      Get-Disk | Where-Object { $PSItem.UniqueId -eq $UniqueId[$I] }
    )
    If ($DiskMatches.Count -ne 1) {
      Throw (
        'Expected one disk with unique id {0}; found {1}.' -f
        $UniqueId[$I], $DiskMatches.Count
      )
    }

    $Partitions = @(
      Get-Partition -DiskNumber:$DiskMatches[0].Number |
        Where-Object { $PSItem.Type -ne 'Reserved' -and $PSItem.Size -gt 1GB } |
        Sort-Object -Property:'Size' -Descending
    )
    If ($Partitions.Count -lt 1) {
      Throw ('No data partition found on disk {0}.' -f $UniqueId[$I])
    }
    $Partition = $Partitions[0]
    $Current = If ([System.Int32][System.Char]$Partition.DriveLetter -ne 0) {
      [System.String]$Partition.DriveLetter
    } Else {
      $Null
    }
    $DiskResult = [PSCustomObject][Ordered]@{
      unique_id = [System.String]$UniqueId[$I]
      disk      = $DiskMatches[0].Number
      partition = $Partition.PartitionNumber
      before    = [System.String]$Current
      after     = [System.String]$Current
      changed   = [System.Boolean]($Current -ne $Targets[$I])
    }
    $Disks += $DiskResult
    $Resolved += [PSCustomObject]@{
      Result = $DiskResult
      Target = $Targets[$I]
    }
  }

  $Moves = @($Resolved | Where-Object { $PSItem.Result.changed })
  $KeptLetters = @(
    $Resolved |
      Where-Object { -not [System.String]::IsNullOrEmpty($PSItem.Result.before) } |
      ForEach-Object { $PSItem.Result.before }
  )
  $Kinds = @{
    2 = 'removable drive'
    3 = 'local volume'
    4 = 'network drive'
    5 = 'CD/DVD drive'
    6 = 'RAM disk'
  }

  # Check every destination before setting Changed or removing any current letter.
  ForEach ($Move In $Moves) {
    $Holders = @(
      Get-CimInstance -ClassName:'Win32_LogicalDisk' -Filter:(
        "DeviceID='{0}:'" -f $Move.Target
      )
    )
    If ($Holders.Count -gt 0 -and $KeptLetters -notcontains $Move.Target) {
      $Holder = $Holders[0]
      $Kind = $Kinds[[System.Int32]$Holder.DriveType]
      If (-not $Kind) {
        $Kind = 'drive of type {0}' -f $Holder.DriveType
      }
      $HeldBy = [PSCustomObject][Ordered]@{
        letter = [System.String]$Move.Target
        kind   = [System.String]$Kind
        label  = [System.String]$Holder.VolumeName
      }
      Throw (
        (
          "Declared letter {0}: is held by a {1} labelled '{2}', which this role does not " +
          'manage. No drive letter was changed. Move it off {0}: and run again.'
        ) -f $Move.Target, $Kind, $Holder.VolumeName
      )
    }
  }

  If ($Moves.Count -gt 0) {
    $Ansible.Changed = $True
  }

  $Assigned = @()
  If ($Moves.Count -gt 0 -and -not $Ansible.CheckMode) {
    ForEach ($Move In ($Moves | Where-Object { $PSItem.Result.before })) {
      $AccessPath = '{0}:\' -f $Move.Result.before
      If ($PSCmdlet.ShouldProcess($AccessPath, 'Remove partition access path')) {
        Remove-PartitionAccessPath -DiskNumber:$Move.Result.disk `
          -PartitionNumber:$Move.Result.partition -AccessPath:$AccessPath
        $Move.Result.after = [System.String]::Empty
      }
    }

    ForEach ($Move In $Moves) {
      $TargetPath = '{0}:' -f $Move.Target
      If ($PSCmdlet.ShouldProcess($TargetPath, 'Set partition drive letter')) {
        Set-Partition -DiskNumber:$Move.Result.disk `
          -PartitionNumber:$Move.Result.partition -NewDriveLetter:$Move.Target
        $Move.Result.after = [System.String]$Move.Target
        $Assigned += $Move
      }
    }

    ForEach ($Move In $Assigned) {
      $ReadBack = Get-Partition -DiskNumber:$Move.Result.disk `
        -PartitionNumber:$Move.Result.partition
      $Now = If ([System.Int32][System.Char]$ReadBack.DriveLetter -ne 0) {
        [System.String]$ReadBack.DriveLetter
      } Else {
        'no letter'
      }
      If ($Now -ne $Move.Target) {
        Throw (
          'Disk {0} read back on {1}: after moving to {2}:' -f
          $Move.Result.unique_id, $Now, $Move.Target
        )
      }
    }
  }

  $Message = If ($Moves.Count -eq 0) {
    'every kept disk is on its declared letter'
  } ElseIf ($Ansible.CheckMode) {
    '{0} kept disk(s) would move' -f $Moves.Count
  } Else {
    '{0} kept disk(s) moved' -f $Moves.Count
  }
  $Result = [PSCustomObject][Ordered]@{
    changed    = [System.Boolean]$Ansible.Changed
    check_mode = [System.Boolean]$Ansible.CheckMode
    disks      = @($Disks)
    held_by    = $HeldBy
    msg        = [System.String]$Message
  }
} Catch {
  $Failure = $PSItem
  $Ansible.Result = [PSCustomObject][Ordered]@{
    changed    = [System.Boolean]$Ansible.Changed
    check_mode = [System.Boolean]$Ansible.CheckMode
    disks      = @($Disks)
    held_by    = $HeldBy
    msg        = [System.String]$Failure.Exception.Message
  }
  $Ansible.Failed = $True
  Throw
}

#endregion --- [ Main ] ---------------------------------------------------------------------- #

#region ------ [ Output ] -------------------------------------------------------------------- #
Write-Debug -Message:'Entering Stage: Output'

$Ansible.Changed = $Result.changed
$Ansible.Result = $Result

If ($StandaloneRun) {
  $Ansible.Result | ConvertTo-Json -Depth:4
}

Write-Debug -Message:'Exiting Script'
#endregion --- [ Output ] -------------------------------------------------------------------- #

#endregion --- [ Script ] -------------------------------------------------------------------- #
