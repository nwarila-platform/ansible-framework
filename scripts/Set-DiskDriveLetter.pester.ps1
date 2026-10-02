#Requires -Version 5.1
# SPDX-FileCopyrightText: 2026 Nicholas Warila
# SPDX-License-Identifier: MIT
<#
    Pester spec for Set-DiskDriveLetter.ps1. The Windows storage cmdlets are shadowed over an
    in-memory disk, partition and logical-disk model, so the full decision surface runs on any
    build host. The write log proves ordering and proves refusals and check modes write nothing.

    Stub state is global because functions invoked from the child script resolve $script: in the
    child scope. The pre-seeded $Ansible object also records property-set order, proving failure
    publication precedes the transport's Failed flag.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

BeforeAll {
  $script:ScriptPath = Join-Path $PSScriptRoot 'Set-DiskDriveLetter.ps1'
  $script:Ids = @('disk-a', 'disk-b', 'disk-c')
  $script:Targets = @('E', 'F', 'G')

  Function New-AnsibleContext {
    Param ([Switch]$CheckMode)

    $global:FakeTransportResult = $Null
    $global:FakeTransportFailed = $False
    $global:FakeTransportEvents = @()
    $Context = [PSCustomObject]@{
      Changed   = $True
      CheckMode = $CheckMode.IsPresent
    }
    $Context | Add-Member -MemberType ScriptProperty -Name 'Result' -Value {
      $global:FakeTransportResult
    } -SecondValue {
      $global:FakeTransportEvents += 'Result'
      $global:FakeTransportResult = $Args[0]
    }
    $Context | Add-Member -MemberType ScriptProperty -Name 'Failed' -Value {
      $global:FakeTransportFailed
    } -SecondValue {
      $global:FakeTransportEvents += 'Failed'
      $global:FakeTransportFailed = [System.Boolean]$Args[0]
    }
    $global:Ansible = $Context
    $global:Ansible
  }

  Function Remove-AnsibleContext {
    Remove-Variable -Name:'Ansible' -Scope:'Global' -Force `
      -ErrorAction:'SilentlyContinue'
  }

  Function Set-FakeThreeDiskState {
    Param ([AllowNull()] [System.Object[]]$Letters)

    $global:FakeDisks = @(
      [PSCustomObject]@{ UniqueId = 'disk-a'; Number = 1 }
      [PSCustomObject]@{ UniqueId = 'disk-b'; Number = 2 }
      [PSCustomObject]@{ UniqueId = 'disk-c'; Number = 3 }
    )
    $global:FakePartitions = @(
      [PSCustomObject]@{
        DiskNumber = 1
        DriveLetter = If ($Null -eq $Letters[0]) { [System.Char]0 } Else { $Letters[0] }
        PartitionNumber = 11
        Size = 10GB
        Type = 'Basic'
      }
      [PSCustomObject]@{
        DiskNumber = 2
        DriveLetter = If ($Null -eq $Letters[1]) { [System.Char]0 } Else { $Letters[1] }
        PartitionNumber = 12
        Size = 20GB
        Type = 'Basic'
      }
      [PSCustomObject]@{
        DiskNumber = 3
        DriveLetter = If ($Null -eq $Letters[2]) { [System.Char]0 } Else { $Letters[2] }
        PartitionNumber = 13
        Size = 30GB
        Type = 'Basic'
      }
    )
  }

  Function New-FakeHolder {
    Param (
      [System.String]$Letter,
      [System.Int32]$DriveType,
      [AllowEmptyString()] [System.String]$Label
    )

    [PSCustomObject]@{
      DeviceID = '{0}:' -f $Letter
      DriveType = $DriveType
      VolumeName = $Label
    }
  }

  Function Get-Disk {
    [CmdletBinding()]
    Param ()

    $global:FakeGetDiskCalls++
    @($global:FakeDisks)
  }

  Function Get-Partition {
    [CmdletBinding()]
    Param (
      [Parameter(Mandatory)] [System.Int32]$DiskNumber,
      [Parameter()] [System.Int32]$PartitionNumber
    )

    $global:FakeGetPartitionCalls++
    @(
      $global:FakePartitions | Where-Object {
        $PSItem.DiskNumber -eq $DiskNumber -and
        (-not $PSBoundParameters.ContainsKey('PartitionNumber') -or
          $PSItem.PartitionNumber -eq $PartitionNumber)
      }
    )
  }

  Function Get-CimInstance {
    [CmdletBinding()]
    Param (
      [Parameter(Mandatory)] [System.String]$ClassName,
      [Parameter(Mandatory)] [System.String]$Filter
    )

    If ($ClassName -ne 'Win32_LogicalDisk' -or
      $Filter -notmatch "^DeviceID='([A-Za-z]):'$"
    ) {
      Throw ('Unexpected CIM query: {0} {1}' -f $ClassName, $Filter)
    }
    $Letter = $Matches[1].ToUpperInvariant()
    $Explicit = @(
      $global:FakeHolders | Where-Object { $PSItem.DeviceID -eq ('{0}:' -f $Letter) }
    )
    If ($Explicit.Count -gt 0) {
      Return $Explicit
    }
    $Partition = @(
      $global:FakePartitions |
        Where-Object { [System.String]$PSItem.DriveLetter -eq $Letter }
    )
    If ($Partition.Count -gt 0) {
      Return [PSCustomObject]@{
        DeviceID = '{0}:' -f $Letter
        DriveType = 3
        VolumeName = 'KEPT'
      }
    }
  }

  Function Remove-PartitionAccessPath {
    [CmdletBinding()]
    Param (
      [Parameter(Mandatory)] [System.Int32]$DiskNumber,
      [Parameter(Mandatory)] [System.Int32]$PartitionNumber,
      [Parameter(Mandatory)] [System.String]$AccessPath
    )

    $Partition = @(
      $global:FakePartitions | Where-Object {
        $PSItem.DiskNumber -eq $DiskNumber -and
        $PSItem.PartitionNumber -eq $PartitionNumber
      }
    )[0]
    $global:FakeWrites += [PSCustomObject]@{
      disk = $DiskNumber
      letter = $AccessPath.Substring(0, 1)
      op = 'remove'
      partition = $PartitionNumber
    }
    $Partition.DriveLetter = [System.Char]0
  }

  Function Set-Partition {
    [CmdletBinding()]
    Param (
      [Parameter(Mandatory)] [System.Int32]$DiskNumber,
      [Parameter(Mandatory)] [System.Int32]$PartitionNumber,
      [Parameter(Mandatory)] [System.String]$NewDriveLetter
    )

    $global:FakeSetAttempts++
    If ($global:FakeThrowSetCall -eq $global:FakeSetAttempts) {
      Throw ('Synthetic Set-Partition failure on call {0}.' -f $global:FakeSetAttempts)
    }
    $PartitionHolder = @(
      $global:FakePartitions | Where-Object {
        [System.String]$PSItem.DriveLetter -eq $NewDriveLetter
      }
    )
    $LogicalHolder = @(
      $global:FakeHolders | Where-Object {
        $PSItem.DeviceID -eq ('{0}:' -f $NewDriveLetter)
      }
    )
    If ($PartitionHolder.Count -gt 0 -or $LogicalHolder.Count -gt 0) {
      Throw ('The requested access path {0}: is already in use.' -f $NewDriveLetter)
    }
    $Partition = @(
      $global:FakePartitions | Where-Object {
        $PSItem.DiskNumber -eq $DiskNumber -and
        $PSItem.PartitionNumber -eq $PartitionNumber
      }
    )[0]
    $global:FakeWrites += [PSCustomObject]@{
      disk = $DiskNumber
      letter = $NewDriveLetter
      op = 'set'
      partition = $PartitionNumber
    }
    If (-not $global:FakeSetIgnored) {
      $Partition.DriveLetter = $NewDriveLetter
    }
  }
}

Describe 'Set-DiskDriveLetter' {
  BeforeEach {
    Set-FakeThreeDiskState -Letters @('E', 'F', 'G')
    $global:FakeHolders = @()
    $global:FakeWrites = @()
    $global:FakeGetDiskCalls = 0
    $global:FakeGetPartitionCalls = 0
    $global:FakeSetAttempts = 0
    $global:FakeThrowSetCall = 0
    $global:FakeSetIgnored = $False
  }

  AfterEach {
    Remove-AnsibleContext
  }

  AfterAll {
    Remove-AnsibleContext
    Remove-Variable -Name @(
      'FakeDisks'
      'FakePartitions'
      'FakeHolders'
      'FakeWrites'
      'FakeGetDiskCalls'
      'FakeGetPartitionCalls'
      'FakeSetAttempts'
      'FakeThrowSetCall'
      'FakeSetIgnored'
      'FakeTransportResult'
      'FakeTransportFailed'
      'FakeTransportEvents'
    ) -Scope:'Global' -Force -ErrorAction:'SilentlyContinue'
  }

  It 'P1 converged: reports unchanged with the exact result schema and no writes' {
    $Command = Get-Command -Name $script:ScriptPath
    $Command.Parameters.ContainsKey('WhatIf') | Should -BeTrue
    $Context = New-AnsibleContext

    & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets | Out-Null

    $Context.Changed | Should -BeFalse
    $Context.Result.check_mode | Should -BeFalse
    $Context.Result.msg | Should -BeExactly 'every kept disk is on its declared letter'
    @($global:FakeWrites).Count | Should -Be 0
    @($Context.Result.PSObject.Properties.Name) | Should -Be @(
      'changed', 'check_mode', 'disks', 'held_by', 'msg'
    )
    ForEach ($Disk In $Context.Result.disks) {
      @($Disk.PSObject.Properties.Name) | Should -Be @(
        'unique_id', 'disk', 'partition', 'before', 'after', 'changed'
      )
    }
  }

  It 'P2 rotation: removes all three letters before assigning all three targets' {
    Set-FakeThreeDiskState -Letters @('F', 'G', 'E')
    $Context = New-AnsibleContext

    & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets | Out-Null

    $Context.Changed | Should -BeTrue
    @($global:FakeWrites.op) | Should -Be @(
      'remove', 'remove', 'remove', 'set', 'set', 'set'
    )
    @($global:FakeWrites.letter) | Should -BeExactly @('F', 'G', 'E', 'E', 'F', 'G')
    @($Context.Result.disks.after) | Should -BeExactly @('E', 'F', 'G')
    @($Context.Result.disks.changed) | Should -Be @($True, $True, $True)
  }

  It 'P3 all three letterless: assigns three targets without removing anything' {
    Set-FakeThreeDiskState -Letters @($Null, $Null, $Null)
    $Context = New-AnsibleContext

    & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets | Out-Null

    $Context.Changed | Should -BeTrue
    @($global:FakeWrites.op) | Should -Be @('set', 'set', 'set')
    @($Context.Result.disks.after) | Should -BeExactly @('E', 'F', 'G')
  }

  It 'P4 mixed: moves only the wrong and letterless disks' {
    Set-FakeThreeDiskState -Letters @('E', 'H', $Null)
    $Context = New-AnsibleContext

    & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets | Out-Null

    @($global:FakeWrites.op) | Should -Be @('remove', 'set', 'set')
    @($global:FakeWrites.letter) | Should -BeExactly @('H', 'F', 'G')
    @($Context.Result.disks.changed) | Should -Be @($False, $True, $True)
    @($Context.Result.disks.after) | Should -BeExactly @('E', 'F', 'G')
  }

  It 'P5 foreign local-volume holder: refuses with exact failure schema and no writes' {
    Set-FakeThreeDiskState -Letters @('D', 'H', 'I')
    $global:FakeHolders = @((New-FakeHolder -Letter 'E' -DriveType 3 -Label 'FOREIGN'))
    $Context = New-AnsibleContext
    $Expected = "Declared letter E: is held by a local volume labelled 'FOREIGN', which this " +
      'role does not manage. No drive letter was changed. Move it off E: and run again.'

    {
      & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets
    } | Should -Throw

    @($global:FakeWrites).Count | Should -Be 0
    $Context.Changed | Should -BeFalse
    $Context.Result.changed | Should -BeFalse
    $Context.Result.check_mode | Should -BeFalse
    $Context.Result.msg | Should -BeExactly $Expected
    @($Context.Result.PSObject.Properties.Name) | Should -Be @(
      'changed', 'check_mode', 'disks', 'held_by', 'msg'
    )
    @($Context.Result.held_by.PSObject.Properties.Name) | Should -Be @(
      'letter', 'kind', 'label'
    )
    $Context.Result.held_by.letter | Should -BeExactly 'E'
    $Context.Result.held_by.kind | Should -Be 'local volume'
    $Context.Result.held_by.label | Should -Be 'FOREIGN'
    @($Context.Result.disks.changed) | Should -Be @($True, $True, $True)
    @($global:FakeTransportEvents) | Should -Be @('Result', 'Failed')
    $Context.Failed | Should -BeTrue
  }

  It 'P6 CD/DVD holder: refuses naming its kind and changes nothing' {
    Set-FakeThreeDiskState -Letters @('D', 'H', 'I')
    $global:FakeHolders = @((New-FakeHolder -Letter 'E' -DriveType 5 -Label 'INSTALL'))
    $Context = New-AnsibleContext

    {
      & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets
    } | Should -Throw

    $Expected = "Declared letter E: is held by a CD/DVD drive labelled 'INSTALL', which this " +
      'role does not manage. No drive letter was changed. Move it off E: and run again.'
    $Context.Result.msg | Should -BeExactly $Expected
    $Context.Result.held_by.kind | Should -Be 'CD/DVD drive'
    $Context.Changed | Should -BeFalse
    $Context.Result.changed | Should -BeFalse
    @($global:FakeWrites).Count | Should -Be 0
  }

  It 'P7 kept-disk holder: permits a rotation and converges it' {
    Set-FakeThreeDiskState -Letters @('F', 'G', 'E')
    $Context = New-AnsibleContext

    & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets | Out-Null

    $Context.Failed | Should -BeFalse
    $Context.Result.held_by | Should -BeNullOrEmpty
    @($global:FakeWrites.op) | Should -Be @(
      'remove', 'remove', 'remove', 'set', 'set', 'set'
    )
    @($Context.Result.disks.after) | Should -BeExactly @('E', 'F', 'G')
  }

  It 'P8 check mode rotation: reports moves while leaving every letter unchanged' {
    Set-FakeThreeDiskState -Letters @('F', 'G', 'E')
    $Context = New-AnsibleContext -CheckMode

    & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets `
      -WhatIf | Out-Null

    $Context.Changed | Should -BeTrue
    $Context.Result.check_mode | Should -BeTrue
    @($global:FakeWrites).Count | Should -Be 0
    @($Context.Result.disks.before) | Should -BeExactly @('F', 'G', 'E')
    @($Context.Result.disks.after) | Should -BeExactly @('F', 'G', 'E')
    @($Context.Result.disks.changed) | Should -Be @($True, $True, $True)
  }

  It 'P8c check mode without WhatIf: the outer gate prevents every write' {
    Set-FakeThreeDiskState -Letters @('F', 'G', 'E')
    $Context = New-AnsibleContext -CheckMode

    & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets | Out-Null

    $Context.Changed | Should -BeTrue
    @($global:FakeWrites).Count | Should -Be 0
    @($Context.Result.disks.after) | Should -BeExactly @('F', 'G', 'E')
  }

  It 'P8b WhatIf with transport check mode false: every guard prevents writes' {
    Set-FakeThreeDiskState -Letters @('F', 'G', 'E')
    $Context = New-AnsibleContext

    & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets `
      -WhatIf | Out-Null

    $Context.Changed | Should -BeTrue
    $Context.Result.check_mode | Should -BeFalse
    $Context.Failed | Should -BeFalse
    @($global:FakeWrites).Count | Should -Be 0
    @($Context.Result.disks.before) | Should -BeExactly @('F', 'G', 'E')
    @($Context.Result.disks.after) | Should -BeExactly @('F', 'G', 'E')
    @($Context.Result.disks.changed) | Should -Be @($True, $True, $True)
  }

  It 'P9 invalid declarations: every refusal precedes the first disk read' {
    $Cases = @(
      @{ Ids = @('disk-a', 'disk-b'); Letters = @('E', 'F', 'G') }
      @{ Ids = @('disk-a'); Letters = @('EE') }
      @{ Ids = @('disk-a'); Letters = @('1') }
      @{ Ids = @('disk-a', 'disk-b'); Letters = @('E', 'e') }
      @{ Ids = @(''); Letters = @('E') }
      @{ Ids = @('disk-a'); Letters = @('') }
      @{ Ids = @('disk-a', 'disk-a'); Letters = @('E', 'F') }
      @{ Ids = @(); Letters = @() }
    )

    ForEach ($Case In $Cases) {
      $global:FakeGetDiskCalls = 0
      $global:FakeWrites = @()
      $Context = New-AnsibleContext
      {
        & $script:ScriptPath -UniqueId $Case.Ids -DriveLetter $Case.Letters
      } | Should -Throw
      $global:FakeGetDiskCalls | Should -Be 0
      @($global:FakeWrites).Count | Should -Be 0
      $Context.Failed | Should -BeTrue
      $Context.Changed | Should -BeFalse
      $Context.Result.changed | Should -BeFalse
      Remove-AnsibleContext
    }
  }

  It 'P10 disk resolution cardinality: refuses zero or two matches after prior resolved pairs' {
    $Context = New-AnsibleContext
    {
      & $script:ScriptPath -UniqueId @('disk-a', 'missing') -DriveLetter @('E', 'F')
    } | Should -Throw
    @($Context.Result.disks).Count | Should -Be 1
    @($global:FakeWrites).Count | Should -Be 0

    Remove-AnsibleContext
    Set-FakeThreeDiskState -Letters @('E', 'F', 'G')
    $global:FakeDisks += @(
      [PSCustomObject]@{ UniqueId = 'duplicate'; Number = 8 }
      [PSCustomObject]@{ UniqueId = 'duplicate'; Number = 9 }
    )
    $Context = New-AnsibleContext
    {
      & $script:ScriptPath -UniqueId @('disk-a', 'duplicate') -DriveLetter @('E', 'F')
    } | Should -Throw
    @($Context.Result.disks).Count | Should -Be 1
    @($global:FakeWrites).Count | Should -Be 0
  }

  It 'P11 no data partition: refuses a disk with no non-reserved partition over 1GB' {
    $global:FakePartitions[0].Size = 1GB
    $Context = New-AnsibleContext

    {
      & $script:ScriptPath -UniqueId @('disk-a') -DriveLetter @('E')
    } | Should -Throw

    $Context.Result.msg | Should -BeExactly 'No data partition found on disk disk-a.'
    @($Context.Result.disks).Count | Should -Be 0
    @($global:FakeWrites).Count | Should -Be 0
  }

  It 'P12 second assignment failure: publishes before failing and exposes the partial state' {
    Set-FakeThreeDiskState -Letters @('F', 'G', 'E')
    $global:FakeThrowSetCall = 2
    $Context = New-AnsibleContext

    {
      & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets
    } | Should -Throw

    @($global:FakeTransportEvents) | Should -Be @('Result', 'Failed')
    $Context.Changed | Should -BeTrue
    $Context.Result.changed | Should -BeTrue
    @($global:FakeWrites.op) | Should -Be @('remove', 'remove', 'remove', 'set')
    @($global:FakeWrites.letter) | Should -BeExactly @('F', 'G', 'E', 'E')
    [System.String]$global:FakePartitions[0].DriveLetter | Should -BeExactly 'E'
    [System.Int32][System.Char]$global:FakePartitions[1].DriveLetter | Should -Be 0
    [System.Int32][System.Char]$global:FakePartitions[2].DriveLetter | Should -Be 0
    @($Context.Result.disks.after) | Should -BeExactly @('E', '', '')
  }

  It 'P12b retry after the partial failure: assigns the two letterless partitions' {
    Set-FakeThreeDiskState -Letters @('E', $Null, $Null)
    $Context = New-AnsibleContext

    & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets | Out-Null

    $Context.Failed | Should -BeFalse
    @($global:FakeWrites.op) | Should -Be @('set', 'set')
    @($global:FakeWrites.letter) | Should -BeExactly @('F', 'G')
    @($Context.Result.disks.after) | Should -BeExactly @('E', 'F', 'G')
  }

  It 'P13 ignored assignment: fails read-back and names the disk' {
    Set-FakeThreeDiskState -Letters @('F', 'G', 'E')
    $global:FakeSetIgnored = $True
    $Context = New-AnsibleContext

    {
      & $script:ScriptPath -UniqueId $script:Ids -DriveLetter $script:Targets
    } | Should -Throw

    @($global:FakeWrites.op) | Should -Be @(
      'remove', 'remove', 'remove', 'set', 'set', 'set'
    )
    $Context.Result.msg |
      Should -BeExactly 'Disk disk-a read back on no letter: after moving to E:'
    $Context.Result.changed | Should -BeTrue
    @($Context.Result.disks.after) | Should -BeExactly @('E', 'F', 'G')
    $Context.Failed | Should -BeTrue
  }

  It 'P14 one kept disk: removes its wrong letter and assigns its target' {
    Set-FakeThreeDiskState -Letters @('H', 'F', 'G')
    $Context = New-AnsibleContext

    & $script:ScriptPath -UniqueId @('disk-a') -DriveLetter @('E') | Out-Null

    $Context.Changed | Should -BeTrue
    @($global:FakeWrites.op) | Should -Be @('remove', 'set')
    @($global:FakeWrites.letter) | Should -BeExactly @('H', 'E')
    @($Context.Result.disks).Count | Should -Be 1
    $Context.Result.disks[0].after | Should -BeExactly 'E'
  }

  It 'P15 largest eligible partition: publishes and uses the larger partition' {
    $global:FakePartitions += [PSCustomObject]@{
      DiskNumber = 1
      DriveLetter = 'H'
      PartitionNumber = 99
      Size = 2GB
      Type = 'Basic'
    }
    $Context = New-AnsibleContext

    & $script:ScriptPath -UniqueId @('disk-a') -DriveLetter @('E') | Out-Null

    $Context.Result.disks[0].partition | Should -Be 11
    @($global:FakeWrites).Count | Should -Be 0
  }

  It 'P16 Reserved exclusion: publishes the converged Basic partition' {
    $global:FakePartitions += [PSCustomObject]@{
      DiskNumber = 1
      DriveLetter = 'H'
      PartitionNumber = 98
      Size = 100GB
      Type = 'Reserved'
    }
    $Context = New-AnsibleContext

    & $script:ScriptPath -UniqueId @('disk-a') -DriveLetter @('E') | Out-Null

    $Context.Result.disks[0].partition | Should -Be 11
    @($global:FakeWrites).Count | Should -Be 0
  }

  It 'P17 lower-case target: writes and reports the upper-case letter' {
    Set-FakeThreeDiskState -Letters @($Null, 'F', 'G')
    $Context = New-AnsibleContext

    & $script:ScriptPath -UniqueId @('disk-a') -DriveLetter @('e') | Out-Null

    $Context.Changed | Should -BeTrue
    @($global:FakeWrites).Count | Should -Be 1
    @($global:FakeWrites.op) | Should -Be @('set')
    @($global:FakeWrites.letter) | Should -BeExactly @('E')
    $Context.Result.disks[0].after | Should -BeExactly 'E'
  }
}
