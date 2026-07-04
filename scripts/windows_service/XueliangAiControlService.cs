using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.ServiceProcess;
using System.Threading;

namespace XueliangAiControl
{
    public class XueliangAiControlService : ServiceBase
    {
        private const string ServiceId = "XueliangAiControlService";
        private static string root = AppDomain.CurrentDomain.BaseDirectory;
        private readonly ManualResetEvent stopEvent = new ManualResetEvent(false);
        private Thread workerThread;
        private Process childProcess;

        public XueliangAiControlService()
        {
            ServiceName = ServiceId;
            CanStop = true;
            CanShutdown = true;
        }

        public static void Main(string[] args)
        {
            if (args.Length > 0 && !string.IsNullOrWhiteSpace(args[0]))
            {
                root = Path.GetFullPath(args[0]);
            }

            if (Environment.UserInteractive)
            {
                var service = new XueliangAiControlService();
                service.OnStart(args);
                Console.WriteLine("Xueliang AI control service wrapper is running. Press Ctrl+C to stop.");
                Console.CancelKeyPress += delegate(object sender, ConsoleCancelEventArgs e)
                {
                    e.Cancel = true;
                    service.OnStop();
                };
                service.workerThread.Join();
                return;
            }

            Run(new XueliangAiControlService());
        }

        protected override void OnStart(string[] args)
        {
            Directory.CreateDirectory(LogDir);
            Log("service wrapper started");
            stopEvent.Reset();
            workerThread = new Thread(RunLoop);
            workerThread.IsBackground = true;
            workerThread.Start();
        }

        protected override void OnStop()
        {
            Log("service wrapper stopping");
            stopEvent.Set();
            StopChild();
            if (workerThread != null && workerThread.IsAlive)
            {
                workerThread.Join(TimeSpan.FromSeconds(20));
            }
            Log("service wrapper stopped");
        }

        protected override void OnShutdown()
        {
            OnStop();
        }

        private static string LogDir
        {
            get { return Path.Combine(root, "logs"); }
        }

        private void RunLoop()
        {
            int failedHealthChecks = 0;
            while (!stopEvent.WaitOne(0))
            {
                try
                {
                    if (childProcess == null || childProcess.HasExited)
                    {
                        StartChild();
                        failedHealthChecks = 0;
                    }
                    else if (!HealthReady())
                    {
                        failedHealthChecks++;
                        if (failedHealthChecks >= 3)
                        {
                            Log("health check failed repeatedly; restarting child");
                            StopChild();
                            failedHealthChecks = 0;
                        }
                    }
                    else
                    {
                        failedHealthChecks = 0;
                    }
                }
                catch (Exception ex)
                {
                    Log("loop error: " + ex);
                }

                stopEvent.WaitOne(TimeSpan.FromSeconds(10));
            }
        }

        private void StartChild()
        {
            string python = Path.Combine(root, ".venv", "Scripts", "python.exe");
            if (!File.Exists(python))
            {
                throw new FileNotFoundException("Missing Python virtual environment", python);
            }

            string stamp = DateTime.Now.ToString("yyyyMMdd-HHmmss");
            string logPath = Path.Combine(LogDir, "control-service-" + stamp + ".log");
            string command = "\"" + python + "\" -m app.control_service >> \"" + logPath + "\" 2>&1";

            var startInfo = new ProcessStartInfo();
            startInfo.FileName = "cmd.exe";
            startInfo.Arguments = "/d /c \"" + command + "\"";
            startInfo.WorkingDirectory = root;
            startInfo.CreateNoWindow = true;
            startInfo.UseShellExecute = false;

            childProcess = Process.Start(startInfo);
            File.WriteAllText(Path.Combine(LogDir, "control-service.pid"), childProcess.Id.ToString());
            Log("started child pid=" + childProcess.Id);
        }

        private void StopChild()
        {
            if (childProcess == null)
            {
                return;
            }

            try
            {
                if (!childProcess.HasExited)
                {
                    Log("stopping child pid=" + childProcess.Id);
                    Process.Start(new ProcessStartInfo
                    {
                        FileName = "taskkill.exe",
                        Arguments = "/PID " + childProcess.Id + " /F /T",
                        CreateNoWindow = true,
                        UseShellExecute = false
                    }).WaitForExit(15000);
                }
            }
            catch (Exception ex)
            {
                Log("failed to stop child: " + ex);
            }
            finally
            {
                childProcess = null;
                string pidFile = Path.Combine(LogDir, "control-service.pid");
                if (File.Exists(pidFile))
                {
                    File.Delete(pidFile);
                }
            }
        }

        private bool HealthReady()
        {
            try
            {
                var request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:7878/health");
                request.Timeout = 3000;
                using (var response = (HttpWebResponse)request.GetResponse())
                {
                    return (int)response.StatusCode >= 200 && (int)response.StatusCode < 500;
                }
            }
            catch
            {
                return false;
            }
        }

        private static void Log(string message)
        {
            Directory.CreateDirectory(LogDir);
            File.AppendAllText(
                Path.Combine(LogDir, "windows-control-service.log"),
                "[" + DateTime.Now.ToString("s") + "] " + message + Environment.NewLine
            );
        }
    }
}
