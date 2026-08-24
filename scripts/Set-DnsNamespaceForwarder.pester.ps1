#Requires -Version 5.1
# SPDX-FileCopyrightText: 2026 Nicholas Warila
# SPDX-License-Identifier: MIT
<#
    Pester spec for Set-DnsNamespaceForwarder.ps1 (org pair convention: every script ships
    with a sibling <Name>.pester.ps1; the pester-matrix workflow runs one leg per pair).

    Runs anywhere, Linux CI included: the DnsClient cmdlets are Windows resource management
    and do not exist on other platforms, so the script confines every platform call to
    Get-DnsClientNrptRule, Add-DnsClientNrptRule, Set-DnsClientNrptRule and
    Remove-DnsClientNrptRule. This file stubs those four around an in-memory table, which
    exercises the whole decision surface -- own, compare in sequence, add, update, remove,
    verify, refuse -- with no policy store at all.

    Stub state lives in $global: variables because inside a function called from a child
    SCRIPT, $script: resolves to the child script's own scope, not this file's.

    Both transports are asserted: the standalone JSON emission and the $Ansible path via the
    inline context below (pairs are self-contained; no imports). Its Changed defaults to $True
    exactly like win_powershell -- so the spec proves the script SETS Changed rather than
    inheriting a default.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

BeforeAll {
  $script:ScriptPath = Join-Path -Path $PSScriptRoot -ChildPath 'Set-DnsNamespaceForwarder.ps1'
  $script:Namespace = '.corp.example.com'
  $script:Comment = 'Managed by openvpn_client'
  $script:Servers = @('10.0.10.5', '10.0.10.6')

  # Inline $Ansible stand-in (org contract: pairs are self-contained, no
  # imports). Faithful to win_powershell: Changed defaults to $True, and only
  # the ratified surface (Changed, CheckMode, Failed, Result) is modeled.
  Function New-AnsibleContext {
    Param ([Switch]$CheckMode)
    $global:Ansible = [PSCustomObject]@{
      Changed   = $True
      CheckMode = $CheckMode.IsPresent
      Failed    = $False
      Result    = $Null
    }
    $global:Ansible
  }

  Function Remove-AnsibleContext {
    Remove-Variable -Name 'Ansible' -Scope 'Global' -Force -ErrorAction 'SilentlyContinue'
  }

  # In-memory policy table. $global:FakeNrpt is a list of rule hashtables shaped like the real
  # objects -- Name (a GUID string), Namespace (a string list), NameServers (a string list),
  # Comment. Get hands out copies; Add appends; Set updates by Name; Remove drops by Name --
  # unless the spec sets $global:FakeWriteIgnored, which models a platform that silently keeps
  # its own shape and is exactly the failure the script's verify pass exists for.
  Function Get-DnsClientNrptRule {
    [CmdletBinding()]
    Param ()

    $global:FakeReads++
    Return @(
      ForEach ($Rule In $global:FakeNrpt) {
        [PSCustomObject]@{
          Comment     = $Rule.Comment
          Name        = $Rule.Name
          NameServers = [System.String[]]@($Rule.NameServers)
          Namespace   = [System.String[]]@($Rule.Namespace)
        }
      }
    )
  }

  Function Add-DnsClientNrptRule {
    [CmdletBinding()]
    Param (
      [Parameter()] [System.String]$Namespace,
      [Parameter()] [System.String[]]$NameServers,
      [Parameter()] [System.String]$Comment
    )

    $global:FakeWrites++
    $global:FakeAdds++
    $global:FakeOps += 'add'
    If (-not $global:FakeWriteIgnored) {
      $global:FakeNrpt += @{
        Comment     = $Comment
        Name        = ('{{{0}}}' -f [System.Guid]::NewGuid().ToString().ToUpperInvariant())
        NameServers = @($NameServers)
        Namespace   = @($Namespace)
      }
    }
  }

  Function Set-DnsClientNrptRule {
    [CmdletBinding()]
    Param (
      [Parameter()] [System.String]$Name,
      [Parameter()] [System.String[]]$NameServers
    )

    $global:FakeWrites++
    $global:FakeSets++
    $global:FakeOps += 'set'
    If (-not $global:FakeWriteIgnored) {
      ForEach ($Rule In $global:FakeNrpt) {
        If ($Rule.Name -eq $Name) {
          $Rule.NameServers = @($NameServers)
        }
      }
    }
  }

  Function Remove-DnsClientNrptRule {
    [CmdletBinding()]
    Param (
      [Parameter()] [System.String]$Name,
      [Parameter()] [Switch]$Force
    )

    $global:FakeWrites++
    $global:FakeRemoves++
    $global:FakeOps += 'remove'
    If (-not $global:FakeWriteIgnored) {
      $global:FakeNrpt = @($global:FakeNrpt | Where-Object { $_.Name -ne $Name })
    }
  }

  Function New-OwnedRule {
    Param ([System.String[]]$NameServers, [System.String]$Namespace = $script:Namespace, [System.String]$Name = '{11111111-2222-3333-4444-555555555555}')
    @{
      Comment     = $script:Comment
      Name        = $Name
      NameServers = @($NameServers)
      Namespace   = @($Namespace)
    }
  }
}

Describe 'Set-DnsNamespaceForwarder' {

  BeforeEach {
    $global:FakeNrpt = @()
    $global:FakeReads = 0
    $global:FakeWrites = 0
    $global:FakeAdds = 0
    $global:FakeSets = 0
    $global:FakeRemoves = 0
    $global:FakeOps = @()
    $global:FakeWriteIgnored = $False
  }

  AfterEach {
    Remove-AnsibleContext
  }

  AfterAll {
    Remove-AnsibleContext
    Remove-Variable -Name 'FakeNrpt', 'FakeReads', 'FakeWrites', 'FakeAdds', 'FakeSets', 'FakeRemoves', 'FakeOps', 'FakeWriteIgnored' `
      -Scope 'Global' -Force -ErrorAction 'SilentlyContinue'
  }

  It 'declares SupportsShouldProcess so the module runs it in check mode' {
    $Command = Get-Command -Name $script:ScriptPath
    $Command.Parameters.ContainsKey('WhatIf') | Should -BeTrue
  }

  Context 'present: convergence decisions' {

    It 'reports no change when the owned rule already carries the declared servers in order, and never writes' {
      $global:FakeNrpt = @((New-OwnedRule -NameServers $script:Servers))

      $Result = & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment | ConvertFrom-Json

      $Result.changed | Should -BeFalse
      @($Result.before) | Should -Be @('10.0.10.5', '10.0.10.6')
      @($Result.after) | Should -Be @('10.0.10.5', '10.0.10.6')
      $global:FakeWrites | Should -Be 0
    }

    It 'treats the same servers in another order as drift, because the resolver tries them in order' {
      $global:FakeNrpt = @((New-OwnedRule -NameServers @('10.0.10.6', '10.0.10.5')))

      $Result = & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment | ConvertFrom-Json

      $Result.changed | Should -BeTrue
      $global:FakeSets | Should -Be 1
      @($global:FakeNrpt[0].NameServers) | Should -Be @('10.0.10.5', '10.0.10.6')
    }

    It 'adds the rule when none exists and verifies the readback' {
      $Result = & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment | ConvertFrom-Json

      $Result.changed | Should -BeTrue
      @($Result.before) | Should -BeNullOrEmpty
      @($Result.after) | Should -Be @('10.0.10.5', '10.0.10.6')
      $global:FakeAdds | Should -Be 1
      $global:FakeSets | Should -Be 0
      @($global:FakeNrpt).Count | Should -Be 1
      $global:FakeNrpt[0].Comment | Should -Be $script:Comment
      @($global:FakeNrpt[0].Namespace) | Should -Be @($script:Namespace)
    }

    It 'updates only the servers of a drifted owned rule, in place, and verifies the readback' {
      $global:FakeNrpt = @((New-OwnedRule -NameServers @('10.0.10.5', '192.0.2.9')))

      $Result = & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment | ConvertFrom-Json

      $Result.changed | Should -BeTrue
      @($Result.before) | Should -Be @('10.0.10.5', '192.0.2.9')
      @($Result.after) | Should -Be @('10.0.10.5', '10.0.10.6')
      $global:FakeSets | Should -Be 1
      $global:FakeAdds | Should -Be 0
      @($global:FakeNrpt).Count | Should -Be 1
      $global:FakeNrpt[0].Name | Should -Be '{11111111-2222-3333-4444-555555555555}'
    }

    It 'treats a renamed namespace as a rename: the old owned rule is removed and the new one added' {
      $global:FakeNrpt = @((New-OwnedRule -NameServers $script:Servers -Namespace '.old.example.com'))

      $Result = & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment | ConvertFrom-Json

      $Result.changed | Should -BeTrue
      @($Result.removed) | Should -Be @('{11111111-2222-3333-4444-555555555555}')
      $global:FakeRemoves | Should -Be 1
      $global:FakeAdds | Should -Be 1
      # The new rule is established before the old one is removed, so a failed add never leaves
      # the host with no rule at all.
      @($global:FakeOps) | Should -Be @('add', 'remove')
      @($global:FakeNrpt).Count | Should -Be 1
      @($global:FakeNrpt[0].Namespace) | Should -Be @($script:Namespace)
    }

    It 'replaces an owned rule that also names other namespaces with one that names the declared namespace alone' {
      $global:FakeNrpt = @(
        @{ Comment = $script:Comment; Name = '{11111111-2222-3333-4444-555555555555}'; NameServers = @($script:Servers); Namespace = @($script:Namespace, '.other.example') }
      )

      $Result = & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment | ConvertFrom-Json

      $Result.changed | Should -BeTrue
      $global:FakeAdds | Should -Be 1
      $global:FakeRemoves | Should -Be 1
      @($global:FakeNrpt).Count | Should -Be 1
      @($global:FakeNrpt[0].Namespace) | Should -Be @($script:Namespace)
    }

    It 'compares namespaces case-insensitively, as DNS does' {
      $global:FakeNrpt = @((New-OwnedRule -NameServers $script:Servers -Namespace '.CORP.Example.COM'))

      $Result = & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment | ConvertFrom-Json

      $Result.changed | Should -BeFalse
      $global:FakeWrites | Should -Be 0
    }

    It 'honours a standalone -WhatIf as check mode: reports the would-be add and writes nothing' {
      $Result = & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment -WhatIf | ConvertFrom-Json

      $Result.changed | Should -BeTrue
      $Result.check_mode | Should -BeTrue
      $global:FakeWrites | Should -Be 0
      @($global:FakeNrpt).Count | Should -Be 0
    }

    It 'compares IPv6 servers in canonical form, not the caller''s spelling' {
      $global:FakeNrpt = @((New-OwnedRule -NameServers @('2001:db8::1', '10.0.10.5')))

      $Result = & $script:ScriptPath -Namespace $script:Namespace -NameServers @('2001:DB8:0000::0001', '10.0.10.5') -Comment $script:Comment | ConvertFrom-Json

      $Result.changed | Should -BeFalse
      $global:FakeWrites | Should -Be 0
    }

    It 'fails loudly when the write does not take, instead of claiming a change' {
      $global:FakeWriteIgnored = $True

      { & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment } | Should -Throw
    }

    It 'leaves rules for other namespaces that it does not own alone' {
      $global:FakeNrpt = @(
        @{ Comment = 'someone else'; Name = '{AAAAAAAA-0000-0000-0000-000000000000}'; NameServers = @('192.0.2.1'); Namespace = @('.other.example') }
      )

      $Result = & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment | ConvertFrom-Json

      $Result.changed | Should -BeTrue
      $global:FakeRemoves | Should -Be 0
      @($global:FakeNrpt).Count | Should -Be 2
      @($global:FakeNrpt[0].NameServers) | Should -Be @('192.0.2.1')
    }
  }

  Context 'absent' {

    It 'removes every owned rule and leaves foreign rules alone' {
      $global:FakeNrpt = @(
        (New-OwnedRule -NameServers $script:Servers),
        (New-OwnedRule -NameServers @('10.0.10.5') -Namespace '.old.example.com' -Name '{22222222-0000-0000-0000-000000000000}'),
        @{ Comment = 'someone else'; Name = '{AAAAAAAA-0000-0000-0000-000000000000}'; NameServers = @('192.0.2.1'); Namespace = @('.other.example') }
      )

      $Result = & $script:ScriptPath -State Absent -Comment $script:Comment | ConvertFrom-Json

      $Result.changed | Should -BeTrue
      @($Result.removed).Count | Should -Be 2
      $global:FakeRemoves | Should -Be 2
      $global:FakeAdds | Should -Be 0
      @($global:FakeNrpt).Count | Should -Be 1
      $global:FakeNrpt[0].Comment | Should -Be 'someone else'
    }

    It 'reports no change when nothing is owned, and never writes' {
      $global:FakeNrpt = @(
        @{ Comment = 'someone else'; Name = '{AAAAAAAA-0000-0000-0000-000000000000}'; NameServers = @('192.0.2.1'); Namespace = @('.other.example') }
      )

      $Result = & $script:ScriptPath -State Absent -Comment $script:Comment | ConvertFrom-Json

      $Result.changed | Should -BeFalse
      $global:FakeWrites | Should -Be 0
    }

    It 'fails loudly when a removal does not take' {
      $global:FakeNrpt = @((New-OwnedRule -NameServers $script:Servers))
      $global:FakeWriteIgnored = $True

      { & $script:ScriptPath -State Absent -Comment $script:Comment } | Should -Throw
    }
  }

  Context 'refusals' {

    It 'refuses to shadow a rule for the namespace that it did not write, and writes nothing' {
      $global:FakeNrpt = @(
        @{ Comment = 'written by hand'; Name = '{BBBBBBBB-0000-0000-0000-000000000000}'; NameServers = @('192.0.2.1'); Namespace = @($script:Namespace) }
      )

      { & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment } | Should -Throw '*did not write*'
      $global:FakeWrites | Should -Be 0
    }

    It 'refuses to choose between two owned rules for one namespace, and writes nothing' {
      $global:FakeNrpt = @(
        (New-OwnedRule -NameServers $script:Servers),
        (New-OwnedRule -NameServers @('10.0.10.5') -Name '{CCCCCCCC-0000-0000-0000-000000000000}')
      )

      { & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment } | Should -Throw '*cannot both be the rule*'
      $global:FakeWrites | Should -Be 0
    }

    It 'rejects a name server that is not an IP address before reading or writing anything' {
      { & $script:ScriptPath -Namespace $script:Namespace -NameServers @('dc01.corp.example.com') -Comment $script:Comment } | Should -Throw '*must be IP addresses*'
      $global:FakeReads | Should -Be 0
      $global:FakeWrites | Should -Be 0
    }

    It 'rejects a server list that is empty after trimming' {
      # Whitespace-only elements pass parameter binding and are what the script's own
      # trim-and-refuse path exists for.
      { & $script:ScriptPath -Namespace $script:Namespace -NameServers @(' ', '   ') -Comment $script:Comment } | Should -Throw '*at least one address*'
      $global:FakeWrites | Should -Be 0
    }

    It 'rejects present without a namespace, and a namespace without the leading dot' {
      { & $script:ScriptPath -NameServers $script:Servers -Comment $script:Comment } | Should -Throw '*leading dot*'
      { & $script:ScriptPath -Namespace 'corp.example.com' -NameServers $script:Servers -Comment $script:Comment } | Should -Throw '*leading dot*'
      $global:FakeWrites | Should -Be 0
    }
  }

  Context '$Ansible transport' {

    It 'sets Changed=$False explicitly on a converged host (transport defaults to $True)' {
      $global:FakeNrpt = @((New-OwnedRule -NameServers $script:Servers))
      $Context = New-AnsibleContext

      $Null = & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment

      $Context.Changed | Should -BeFalse
      $Context.Result.changed | Should -BeFalse
      $Context.Result.namespace | Should -Be $script:Namespace
      $Context.Result.state | Should -Be 'Present'
      $global:FakeWrites | Should -Be 0
    }

    It 'reports Changed with before and after after converging' {
      $Context = New-AnsibleContext

      $Null = & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment

      $Context.Changed | Should -BeTrue
      @($Context.Result.after) | Should -Be @('10.0.10.5', '10.0.10.6')
      $global:FakeAdds | Should -Be 1
    }

    It 'honors CheckMode: reports would-change and writes nothing' {
      # -WhatIf reproduces the transport: win_powershell injects it for a SupportsShouldProcess
      # script in check mode, and the script must survive it rather than lose its setup.
      $Context = New-AnsibleContext -CheckMode

      $Null = & $script:ScriptPath -Namespace $script:Namespace -NameServers $script:Servers -Comment $script:Comment -WhatIf

      $Context.Changed | Should -BeTrue
      $Context.Result.check_mode | Should -BeTrue
      $Context.Result.msg | Should -BeLike '*would resolve*'
      $Context.Result.msg | Should -BeLike '*no stale owned rules*'
      $global:FakeWrites | Should -Be 0
    }

    It 'honors CheckMode for absent: reports the would-be removals and writes nothing' {
      $global:FakeNrpt = @((New-OwnedRule -NameServers $script:Servers))
      $Context = New-AnsibleContext -CheckMode

      $Null = & $script:ScriptPath -State Absent -Comment $script:Comment -WhatIf

      $Context.Changed | Should -BeTrue
      @($Context.Result.removed).Count | Should -Be 1
      $global:FakeWrites | Should -Be 0
      @($global:FakeNrpt).Count | Should -Be 1
    }
  }
}
