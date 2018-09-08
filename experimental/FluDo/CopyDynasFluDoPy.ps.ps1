# Purpose: 
# ========
# Look for dynalog files from NAS and copy $n days worth to a local
# folder. 
# 
#
# Inputs (set once in this file at the beginning):
# =======
# $LA1_dyna		: NAS path to look for LA1 dynalogs
# $LA2_dyna		: NAS path to look for LA2 dynalogs
# $LA3_dyna		: NAS path to look for LA3 dynalogs
# $LA4_dyna		: NAS path to look for LA4 dynalogs
#
# $n_d			: look for files in the last $n_d days
# $n_m          : look for files in the last $n_m minutes
# $dest_dir		: path to move stuff to

Write-Host "Num Args:" $args.Length

$LA1_dyna = '\\your]path' 
$LA3_dyna = '\\your]path' 
$LA4_dyna = '\\your]path' 

$n_m = -30
$src_dir = ''
$dest_dir = '' #D:\Temp\dyna_LA4'

# Read-Host "How far back in time shall I search for dynalogs? Press a => 10 mins ago; b => 30 minutes ago; c=> 3 hours ago; d => 1 day ago; q for quit"
$what_timespan =$args[0]
Write-Host "Selected time limit:"$args[0]


<# while("a","b","c", "d", "q" -notcontains $what_timespan)
{
    $what_timespan = Read-Host "press a, c, c, d, or q"
} #>

switch ($what_timespan)
{
    a { $n_m = -10 }
    b { $n_m = -30 }
    c { $n_m = -180 }
    d { $n_m = -1440 }
    q { exit }
    default {'Did not get valid input' | out-host }
}

$which_machine =$args[1]
Write-Host "Selected m/c:"$args[1]


<#Read-Host "Choose a machine to copy dynalogs from.  Press 1, 3, or 4 for LA1, LA3, or LA4; press q to quit"

<# while("1","3","4" -notcontains $which_machine)
{
    $which_machine = Read-Host "press 1, 3, 4, or q"
} #>

switch ($which_machine)
{
    1 { $src_dir = $LA1_dyna; $dest_dir = 'D:\Temp\dyna_LA1' }
    3 { $src_dir = $LA3_dyna; $dest_dir = 'D:\Temp\dyna_LA3' }
    4 { $src_dir = $LA4_dyna; $dest_dir = 'D:\Temp\dyna_LA4' }
    default {'No valid machine ' | out-host }
}


cd $src_dir

gci . | where-object {$_.CreationTime -gt ((Get-Date).AddMinutes($n_m)) } | Out-host

$response ="y"#Read-Host "Continue (y/n)?"

<# while("y","n" -notcontains $response)
{
    $response = Read-Host "press y or n"
}
 #>
# AddDays(-7) is to find files in the last week
if (  "y" -contains $response ) 
{
    gci . | where-object {$_.CreationTime -gt ((get-date).AddMinutes($n_m)) } | foreach-object {copy-item $_.FullName -destination $dest_dir}

}
 
