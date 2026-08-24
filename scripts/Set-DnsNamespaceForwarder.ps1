#Requires -Version 5.1
# SPDX-FileCopyrightText: 2026 Nicholas Warila
# SPDX-License-Identifier: MIT

<#
    .SYNOPSIS
        Holds the Name Resolution Policy Table rules one caller owns: present, exactly one rule
        pinning a namespace to declared servers in declared order; absent, none at all.

    .DESCRIPTION
        A multi-homed host answers a name from whichever adapter's resolver replies first, and
        a cloud resolver answers NXDOMAIN for a private realm faster than a domain controller
        across a tunnel answers with a record. The Name Resolution Policy Table is how Windows
        pins one namespace to named servers regardless of adapter -- the conditional forwarder a
        domain join needs -- and no native Ansible module manages it, which is what routes this
        to the role's first-class script convention.

        OWNERSHIP IS THE COMMENT. Every rule carrying the caller's comment is the caller's,
        whatever namespace it names, so the script can hold the whole set: present means exactly
        one owned rule naming the declared namespace ALONE and no owned rule for any other -- a
        namespace renamed in the playbook is a rename, not a second rule stranded beside the
        first -- and absent means no owned rule at all. A rule for the declared namespace carrying a DIFFERENT
        comment is refused rather than shadowed: a second resolver policy for a realm is a
        decision for a person, not a side effect of a converge. Two owned rules for one namespace
        cannot both be the rule, and choosing between them would be a guess, so that is refused
        too.

        Read -> compare -> mutate only the drift -> re-acquire and verify -> ONE result object.
        Servers compare as a SEQUENCE of canonical addresses: Windows tries them in the order
        given, so primary and secondary swapped is a different policy and is converged as one;
        an address is compared in the form the stack reads it back, not the caller's spelling.
        Apply-and-verify: after a write the rules are read again and must be exactly the declared
        set, so a write that did not take fails the run instead of reporting a change that did
        not happen. The result payload carries server addresses, namespaces and rule names, never
        anything secret.

        Org scripts are a single straightforward process stage in the org script template's
        architecture: one [ Script ] region carrying [ Initialization ] (strict mode, transport
        detection, input normalization), [ Main ] (read -> compare -> apply -> verify -> build
        ONE result object), and [ Output ] (the same object to $Ansible or as JSON).

        Shipped by the org three-file convention: developed under scripts/ with its sibling
        Set-DnsNamespaceForwarder.pester.ps1 spec, while the openvpn_client role carries
        files/Set-DnsNamespaceForwarder.ps1.stub, which the build resolves by dropping this
        file into the role.

    .PARAMETER Comment
        The marker the caller stamps on its rules and finds them by again. One caller, one
        marker; every rule carrying it is the caller's, and a rule for the declared namespace
        carrying any other comment is refused, never replaced.

    .PARAMETER DebugLevel
        Three-digit control string configuring independent debugging functions, one digit each.
        First digit: ErrorActionPreference (0 SilentlyContinue, 1 Stop, 2 Continue, 3 Inquire,
        4 Ignore, 5 Suspend). Second digit: Set-PSDebug (0 off, 1 trace 1, 2 trace 2,
        3 trace 1 + step, 4 trace 2 + step). Third digit: Set-StrictMode (0 off, 1-3 that
        version). Default '103': stop on error, no tracing, strict mode 3.

    .PARAMETER LogLevel
        Six-digit control string setting the preference for each stream, in the order Verbose,
        Debug, Information, Warning, Error, Fatal. Each digit is an ActionPreference
        (0 SilentlyContinue, 1 Stop, 2 Continue, 3 Inquire, 4 Ignore, 5 Suspend).

    .PARAMETER NameServers
        The resolvers the namespace is answered by, as IPv4 or IPv6 addresses, in the order the
        resolver tries them. Required when State is Present; ignored when Absent.

    .PARAMETER Namespace
        The namespace the rule covers, with the leading dot that makes it cover the domain and
        everything beneath it -- '.corp.example.com'. Stored by Windows exactly as given.
        Required when State is Present; ignored when Absent.

    .PARAMETER State
        Present holds exactly one owned rule, for Namespace, with NameServers in order, and
        removes any other owned rule. Absent removes every owned rule. Default Present.

    .EXAMPLE
        .\Set-DnsNamespaceForwarder.ps1 -Namespace '.corp.example.com' -NameServers '10.0.10.5', '10.0.10.6' -Comment 'Managed by openvpn_client'

    .EXAMPLE
        .\Set-DnsNamespaceForwarder.ps1 -State Absent -Comment 'Managed by openvpn_client'

    .OUTPUTS
        System.String -- standalone, the result object as JSON: after, before, changed,
        check_mode, msg, namespace, removed and state. Under the transport it is $Ansible.Result.
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
    Mandatory = $True,
    ParameterSetName = 'default',
    ValueFromPipeline = $False,
    ValueFromPipelineByPropertyName = $False
  )]
  [ValidateNotNullOrEmpty()]
  [System.String]
  $Comment,

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
    Mandatory = $False,
    ParameterSetName = 'default',
    ValueFromPipeline = $False,
    ValueFromPipelineByPropertyName = $False
  )]
  [AllowEmptyCollection()]
  [System.String[]]
  $NameServers = @(),

  [Parameter(
    DontShow = $False,
    Mandatory = $False,
    ParameterSetName = 'default',
    ValueFromPipeline = $False,
    ValueFromPipelineByPropertyName = $False
  )]
  [AllowEmptyString()]
  [System.String]
  $Namespace = '',

  [Parameter(
    DontShow = $False,
    Mandatory = $False,
    ParameterSetName = 'default',
    ValueFromPipeline = $False,
    ValueFromPipelineByPropertyName = $False
  )]
  [ValidateSet('Present', 'Absent')]
  [System.String]
  $State = 'Present'
)

#region ------ [ Script ] -------------------------------------------------------------------- #

#region ------ [ Initialization ] ------------------------------------------------------------ #
Write-Debug -Message:'Entering Stage: Initialization'

# The module runs this script in check mode because it declares SupportsShouldProcess, and injects
# -WhatIf when it does. This script decides check mode from $Ansible.CheckMode, so -WhatIf is
# neutralised here; left on, it would suppress the New-Variable setup below and the cleanups. The
# request is remembered first, so a standalone caller's -WhatIf still means check mode.
$WhatIfRequested = [System.Boolean]$WhatIfPreference
$WhatIfPreference = $false

# Initialize STATIC log level names, indexed by LogLevel digit position.
New-Variable -Force -Name:'LOG_LEVELS' -Option:('Private', 'ReadOnly') -Value:(
  [System.String[]]@('Verbose', 'Debug', 'Information', 'Warning', 'Error', 'Fatal')
)

# Initialize the custom stream preferences; the built-in ones already exist.
New-Variable -Verbose:$False -Force -Name:'ErrorPreference' -Value:(
  [System.Management.Automation.ActionPreference]::Stop
)
New-Variable -Verbose:$False -Force -Name:'FatalPreference' -Value:(
  [System.Management.Automation.ActionPreference]::Stop
)

# Configure log levels based on the LogLevel parameter.
For ($L = 0; $L -lt 6; $L++) {
  Set-Variable -Verbose:$False -Force -Name:('{0}Preference' -f $LOG_LEVELS[$L]) -Value:(
    [System.Int32]::Parse([System.String]$LogLevel[$L]) -as [System.Management.Automation.ActionPreference]
  )
}

# Configure the debug levels: first digit ErrorActionPreference, second digit
# Set-PSDebug, third digit Set-StrictMode.
$ErrorActionPreference = [System.Management.Automation.ActionPreference][System.Int32]::Parse($DebugLevel.Substring(0, 1))
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

# Universal trap used to help with debugging efforts. The original template's
# Wait-Debugger/Exit are interactive-host machinery; under the Ansible
# transport the trap logs and rethrows (Break) so the task fails honestly.
Trap {
  # Diagnostics are wrapped so a partially-populated error record can never
  # replace the original failure with a StrictMode property error.
  Try {
    If ($PSItem.Exception.PSObject.Properties.Name -contains 'ErrorRecord') {
      Write-Debug -Message:(
        'Failed to execute command: {0}' -f [System.String]$PSItem.Exception.ErrorRecord.InvocationInfo.Line
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

# Under win_powershell the transport provides $Ansible; standalone (a dev
# shell or a Pester spec) it does not, so the script creates a faithful stub.
$StandaloneRun = $Null -eq (Get-Variable -Name:'Ansible' -ValueOnly -ErrorAction:'SilentlyContinue')
If ($StandaloneRun) {
  $Ansible = [PSCustomObject]@{
    Changed   = $True
    CheckMode = $WhatIfRequested
    Failed    = $False
    Result    = $Null
  }
}

# Input normalization, completed here so Main starts clean. Present needs a namespace in the
# leading-dot form that covers the domain and everything beneath it, and at least one server that
# is an address the resolver can be handed as-is -- a name here would itself need resolving
# through the rule it defines. Servers are trimmed, canonicalised and de-duplicated IN THE
# CALLER'S ORDER, because order is the order the resolver tries them. The server list is
# normalized into a NEW variable rather than back into its parameter: a parameter variable
# re-runs its validation attributes on assignment, so an empty result would surface as a binding
# error instead of the contract violation it is. The namespace is trimmed in place, which its
# AllowEmptyString attribute cannot refuse. Absent ignores both inputs: it removes every owned
# rule, whatever they name.
$Present = $State -eq 'Present'
$Namespace = $Namespace.Trim()
$Servers = @()
If ($Present) {
  If ($Namespace -notmatch '^\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)*$') {
    Throw ('Namespace must be a domain with a leading dot, such as .corp.example.com; received ''{0}''.' -f $Namespace)
  }
  $Servers = @(
    ForEach ($Server In $NameServers) {
      $Candidate = [System.String]$Server
      $Candidate = $Candidate.Trim()
      If ([System.String]::IsNullOrEmpty($Candidate)) {
        Continue
      }
      $Address = $Null
      If (-not [System.Net.IPAddress]::TryParse($Candidate, [Ref]$Address)) {
        Throw ('NameServers must be IP addresses; received {0}.' -f $Candidate)
      }
      # The CANONICAL form of the address, not the caller's spelling: the stack reads an IPv6
      # address back lower-cased and without leading zeros, and comparing the caller's form
      # would report drift on every converge and then fail the verify.
      $Address.ToString()
    }
  )
  $Servers = @($Servers | Select-Object -Unique)
  If ($Servers.Count -eq 0) {
    Throw 'NameServers must name at least one address after trimming.'
  }
}

#endregion --- [ Initialization ] ------------------------------------------------------------ #

#region ------ [ Main ] ---------------------------------------------------------------------- #
Write-Debug -Message:'Entering Stage: Main'

# No change is the default: a throw in the reads below must not inherit the transport's true.
$Ansible.Changed = $False

# Every rule on the host, split three ways: the ones this caller owns (by comment, whatever they
# name), the one owned rule that names EXACTLY the declared namespace and nothing else, and any
# rule naming that namespace that someone ELSE wrote. Namespace is a list on the rule object: a
# foreign rule is foreign if the list merely contains the namespace, but an owned rule is only
# kept if the list IS the namespace -- a rule that also names something else carries policy this
# caller never declared and is replaced. The comment is stringified before comparing because an
# unset comment reads back as $Null.
$Rules = @(Get-DnsClientNrptRule)
$Owned = @($Rules | Where-Object { [System.String]$PSItem.Comment -ceq $Comment })
$Foreign = @()
$Keep = @()
If ($Present) {
  # Namespaces compare case-insensitively, as DNS names do and as -contains already does; the
  # ownership marker compares exactly, because it is a token, not a name.
  $Foreign = @(
    $Rules | Where-Object {
      @($PSItem.Namespace) -contains $Namespace -and [System.String]$PSItem.Comment -cne $Comment
    }
  )
  $Keep = @(
    $Owned | Where-Object {
      @($PSItem.Namespace).Count -eq 1 -and [System.String]@($PSItem.Namespace)[0] -eq $Namespace
    }
  )
}
$KeepNames = @($Keep | ForEach-Object { [System.String]$PSItem.Name })
$Stale = @($Owned | Where-Object { $KeepNames -notcontains [System.String]$PSItem.Name })

If ($Foreign.Count -gt 0) {
  Throw (
    'A Name Resolution Policy Table rule for {0} exists that this role did not write (comment ' +
    '''{1}''). Refusing to shadow it: a second resolver policy for the namespace is a decision ' +
    'for a person.'
  ) -f $Namespace, [System.String]$Foreign[0].Comment
}
If ($Keep.Count -gt 1) {
  Throw (
    'Found {0} Name Resolution Policy Table rules for {1} carrying the comment ''{2}''. Two rules ' +
    'cannot both be the rule, and choosing one would be a guess.'
  ) -f $Keep.Count, $Namespace, $Comment
}

$Before = @()
If ($Keep.Count -eq 1) {
  $Before = @(@($Keep[0].NameServers) | ForEach-Object { [System.String]$PSItem })
}

# Sequences compare as their joins -- a form that is defined for an empty side too, which
# Compare-Object's reference argument is not on Windows PowerShell 5.1.
$ServersDiffer = ($Before -join ',') -cne ($Servers -join ',')
$RuleChanged = $Present -and (($Keep.Count -eq 0) -or $ServersDiffer)
$Changed = ($Stale.Count -gt 0) -or $RuleChanged
$After = $Before

If ($Changed) {
  $After = $Servers
  If (-not $Ansible.CheckMode) {
    # The declared rule is established FIRST and the stale ones removed after, so a failure in
    # the add leaves the old rule resolving the old namespace rather than leaving nothing at all.
    If ($Present) {
      If ($Keep.Count -eq 0) {
        $Null = Add-DnsClientNrptRule -Namespace:$Namespace -NameServers:$Servers -Comment:$Comment
      } ElseIf ($ServersDiffer) {
        $Null = Set-DnsClientNrptRule -Name:$Keep[0].Name -NameServers:$Servers
      }
    }
    ForEach ($Rule In $Stale) {
      Remove-DnsClientNrptRule -Name:$Rule.Name -Force
    }

    # Prove the writes took. Ownership is read again by the same test, and must be exactly the
    # declared set -- nothing owned for any other namespace, and for present, one rule carrying
    # exactly the declared servers in order. A write the platform silently adjusted would
    # otherwise report changed on every converge, which is the defect this script exists to avoid.
    $Final = @(Get-DnsClientNrptRule | Where-Object { [System.String]$PSItem.Comment -ceq $Comment })
    If ($Present) {
      $Exact = (
        $Final.Count -eq 1 -and
        @($Final[0].Namespace).Count -eq 1 -and
        [System.String]@($Final[0].Namespace)[0] -eq $Namespace
      )
      If (-not $Exact) {
        Throw (
          'Expected exactly one owned rule, for {0} alone, after the write; found {1} owned rule(s).'
        ) -f $Namespace, $Final.Count
      }
      $After = @(@($Final[0].NameServers) | ForEach-Object { [System.String]$PSItem })
      If (($After -join ',') -cne ($Servers -join ',')) {
        Throw (
          'The rule for {0} read back with servers {1} after declaring {2}. Refusing to report ' +
          'convergence.'
        ) -f $Namespace, ($After -join ', '), ($Servers -join ', ')
      }
    } ElseIf ($Final.Count -ne 0) {
      Throw ('Expected no owned rules after the removal; found {0}.' -f $Final.Count)
    }
  }
}

$Result = [PSCustomObject]@{
  after      = [System.String[]]$After
  before     = [System.String[]]$Before
  changed    = [System.Boolean]$Changed
  check_mode = [System.Boolean]$Ansible.CheckMode
  # Two facts make the sentence: what happened to the declared rule, and what happened to stale
  # ones. Check mode speaks in the conditional.
  msg        = @(
    $(If (-not $Present) {
        'no rule declared'
      } ElseIf ($RuleChanged) {
        '{0} {1} through {2}' -f $Namespace, $(If ($Ansible.CheckMode) { 'would resolve' } Else { 'now resolves' }), ($Servers -join ', ')
      } Else {
        '{0} already resolves through {1}' -f $Namespace, ($Servers -join ', ')
      })
    $(If ($Stale.Count -gt 0) {
        '{0} stale owned rule(s) {1}' -f $Stale.Count, $(If ($Ansible.CheckMode) { 'would be removed' } Else { 'removed' })
      } Else {
        'no stale owned rules'
      })
  ) -join '; '
  namespace  = [System.String]$Namespace
  removed    = [System.String[]]@($Stale | ForEach-Object { [System.String]$PSItem.Name })
  state      = [System.String]$State
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
